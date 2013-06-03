import types
import random
import json
import hashlib
import time
import string
import tarfile
import os
import mailbox
import logging

from pytz import utc
from datetime import datetime, timedelta
from django.db import transaction
from inboxen.models import Attachment, Tag, Alias, Domain, Email, Statistic
from django.contrib.auth.models import User
from celery import task, chain, group
from inboxen.helper.user import null_user, user_profile
from inboxen.helper.alias import gen_alias
from inboxen.helper.mail import send_email, make_message

##
# Data liberation
##
@task
@transaction.commit_on_success
def liberate(user, options={}):
    result = chain(
        liberate_user.s(user),
        liberate_aliases.s(user),
        liberate_emails.s(user, options=options)
    )()
    result = [result.get(), result.parent.get(), result.parent.parent.get()]

    # todo: reuse previously made alias if one does exist.
    alias = None
 
    if not alias:
        # okay first time, lets make an alias
        alias = Alias(
            alias=gen_alias(5),
            domain=random.choice(Domain.objects.all()),
            user=user,
            created=datetime.now(utc),
            deleted=False
        )
        alias.save()
        tags = ["Inboxen", "data", "liberation"]
        for i, tag in enumerate(tags):
            tags[i] = Tag(tag=tag, alias=alias)
            tags[i].save()
    
    # right now we need to take the result and make attachments
    attachments = []
    for data in result:
        if data["file"]:
            # store as path
            a = Attachment(
                path=data["data"],
                content_type=data["type"],
                content_disposition=data["name"],
            )
        else:
            # store as regular attachment in db
            a = Attachment(
                data=data["data"],
                content_type=data["type"],
                content_disposition=data["name"]
            )
        a.save()
        attachments.append(a)

    body = """
    Hello,

    You recently requested your data. All the data you have is here excluding:

    - Your password (this is hashed[1] and salted[2] so is a string of nonsense)
    - Your salt[2] (this is used help secure the storage of your password)

    We don't disclose them as those do not change due to data liberation, since they don't
    give any value to you they just reduce the security. All your other data has been given to you though.
    
    You should find attached to this email all the data Inboxen has.

    Thanks,
    The Inboxen Team.

    --
    [1] - https://en.wikipedia.org/wiki/Hash_function
    [2] - https://en.wikipedia.org/wiki/Salt_%28cryptography%29
    """

    send_email(
        user=user, 
        alias=alias,
        sender="support@inboxen.org",
        subject="Data Liberation",
        body=body,
        attachments=attachments,
    ) 

@task
def liberate_user(user):
    data = {
        "preferences":{}
    }

    # user's preferences
    profile = user_profile(user)
    if profile.html_preference == 0:
        data["preferences"]["html_preference"] = "Reject HTML"
    elif profile.html_preference == 1:
        data["preferences"]["html_preference"] = "Prefer plain-text"
    else:
        data["preferences"]["html_preference"] = "Prefer HTML"

    data["preferences"]["pool_amount"] = profile.pool_amount

    # user data
    data["username"] = user.username
    data["is_staff"] = user.is_staff
    data["is_superuser"] = user.is_superuser
    data["last_login"] = user.last_login.isoformat()
    data["join_date"] = user.date_joined.isoformat()
    data["groups"] = [str(group) for group in user.groups.all()]

    data = json.dumps(data)

    return {
        "data":data,
        "type":"text/json",
        "name":"User Data",
        "file":False,
    }

@task
def liberate_aliases(result, user):
    data = {}

    aliases = Alias.objects.filter(user=user)
    for alias in aliases:
        email = "%s@%s" % (alias.alias, alias.domain)
        tags = [tag.tag for tag in Tag.objects.filter(alias=alias)]
        data[email] = {
            "created":alias.created.isoformat(),
            "deleted":alias.deleted,
            "tags":tags,
        }

    data = json.dumps(data)

    return {
        "data":data,
        "type":"text/json",
        "name":"Aliases",
        "file":False,
    }

@task
def liberate_emails(result, user, options={}):
    """ Makes a maildir of all their emails """
    # first we need to come up with a temp name
    rstr = ""
    for i in range(7):
        rstr += string.ascii_letters[random.randint(0, 50)]
    fname = "/tmp/mkdir%s_%s_%s_%s" % (time.time(), os.getpid(), rstr, hashlib.sha256(user.username + rstr).hexdigest()[:50])
    
    # now make the maildir
    if "mailType" in options:
        if options["mailType"] == "maildir":
            mdir = mailbox.Maildir(fname)
        elif options["mailType"] == "mailbox":
            fname += ".mbox" # they should have this file extension
            mdir = mailbox.Mailbox(fname)
        else:
            raise Exception("Unknown mailType: %s" % options["mailType"])
    else:
        # default is maildir
        mdir = mailbox.Maildir(fname)

    # right
    limit = liberate_make_message.rate_limit
    try:
        mdir.lock()
    except NotImplementedError:
        # we don't care, mailbox raises this
        pass
    while Email.objects.filter(user=user)[:limit].exists():
        for email in Email.objects.filter(user=user)[:limit]:
            msg = liberate_make_message.delay(mdir, email)
            print msg

    mdir.flush()
    try:
        mdir.unlock()
    except NotImplementedError:
        # same as lock, we don't care, mailbox raises
        pass
    # now we need to tar this puppy up!
    if "compressType" in options:
        if options["compressType"] == "tar.gz":
            fname += ".tar.gz"
            tar = tarfile.open(fname, "w:gz")
        elif options["compressType"] == "tar.bz2":
            fname += "tar.bz2"
            tar = tarfile.open(fname, "w:bz2")
        else:
            raise Exception("Unknown compressType: %s" % options["compressType"])
    else:
        # default is tar.gz
        fname += "tar.gz"
        tar = tarfile.open(fname, "w:gz")

    tar.add("%s/" % fname) # directories are added recursively by default
    tar.close()

    # right now we just wanna throw this into an attachment
    # at some point (soon) we need to get it so attachments can live on the filesystem

    return {
        "data":fname,
        "type":"application/x-gzip",
        "name":"Tarball of emails as Maildir",
        "file":True,
    }

@task(rate=100)
def liberate_make_message(mdir, message):
    """ Takes a message and makes it """
    msg = make_message(message)
    mdir.add(str(msg))
    mdir.flush()
    return True

##
# Statistics
##

@task
@transaction.commit_on_success
def statistics():
    # get user statistics
    user_count = User.objects.all().count()
    new_count =  User.objects.filter(date_joined__gte=datetime.now(utc) - timedelta(days=1)).count()
    active_count = User.objects.filter(last_login__gte=datetime.now(utc) - timedelta(days=7)).count()

    stat = Statistic(
        user_count=user_count,
        new_count=new_count,
        active_count=active_count,
        date=datetime.now(utc),
    )

    stat.save()

    logging.info("Saved statistics (%s)" % stat.date)


##
# Alias stuff
##
@task(default_retry_delay=5 * 60) # 5 minutes
@transaction.commit_on_success
def delete_alias(email, user=None):
    if type(email) in [types.StringType, types.UnicodeType]:
        if not user:
            raise Exception("Need to give username")
        alias, domain = email.split("@", 1)
        try:
            domain = Domain.objects.get(domain=domain)
            alias = Alias.objects.get(alias=alias, domain=domain, user=user)
        except Alias.DoesNotExist:
            return False
    else:
        user = email.user
        alias = email

    # delete emails
    task_result = None
    limit = int(delete_email.rate_limit)
    while Email.objects.filter(inbox=alias, user=user)[:limit].exists():
        if not task_result:
            emails = Email.objects.filter(inbox=alias, user=user)[:limit]
            email_group = []
            for epost in emails:
                email_group.append(delete_email.subtask((epost,)))
        
            task_result = group(email_group).apply_async()

        else:
            if task_result.ready():
                # batch task has completed.
                task_result = None
        
        time.sleep(0.1) # lets not completely hammar the CPU


    # delete tags
    tags = Tag.objects.filter(alias=alias)
    tags.delete()

    # okay now mark the alias as deleted
    alias.created = datetime.fromtimestamp(0)
    alias.save()

    return True

@task(rate_limit=100)
@transaction.commit_on_success
def delete_email(email):
    email.delete()
    return True

@task(ignore_result=True, store_errors_even_if_ignored=True)
@transaction.commit_on_success
def disown_alias(result, alias, futr_user=None):
    if not futr_user:
        futr_user = null_user()

    alias.user = futr_user
    alias.save()

@task(max_retries=None, default_retry_delay=10 * 60, ignore_result=True, store_errors_even_if_ignored=True)
@transaction.commit_on_success
def delete_user(user):
    alias = Alias.objects.filter(user=user).exists()
    if alias:
        logging.info("Defering user deletion to later")
        # defer this task until later
        raise delete_user.retry(
            exc=Exception("User still has aliases"),
            countdown=60)
    else:
        logging.info("Deleting user %s" % user.username)
        user.delete()
    return True

@task(default_retry_delay=10 * 60, ignore_result=True, store_errors_even_if_ignored=True)
@transaction.commit_on_success
def delete_account(user):
    # first we need to make sure the user can't login
    user.set_unusable_password()
    user.save()

    # first delete all aliases
    alias = Alias.objects.filter(user=user)[:100]
    for a in alias:
        chain(delete_alias.s(a), disown_alias.s(a)).delay()

    # now scrub some more info we have
    user_profile(user).delete()
    
    # finally delete the user object only when 
    # all the alias/email tasks have finished
    delete_user.delay(user) 