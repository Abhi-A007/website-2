##
#    Copyright (C) 2013 Jessica Tallon & Matt Molyneaux
#   
#    This file is part of Inboxen front-end.
#
#    Inboxen front-end is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Inboxen front-end is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with Inboxen front-end.  If not, see <http://www.gnu.org/licenses/>.
##

from django.conf import settings
from django.conf.urls import patterns, include, url

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', 'inboxen.views.home'),
    
    url(r'^help/contact/', 'inboxen.views.contact'),

    url(r'^user/login/', 'django.contrib.auth.views.login', 
        {
            'template_name': 'login.html',
            'extra_context': {
                'page':'Login',
                'registration_enabled':settings.ENABLE_REGISTRATION,
            },
        },
    ),
    url(r'^user/register/', 'inboxen.views.login.register'),
    url(r'^user/profile/(?P<page>\d+)', 'inboxen.views.profile.profile'),
    url(r'^user/profile/', 'inboxen.views.profile.profile'),
    url(r'^user/settings/', 'inboxen.views.profile.settings'),
    url(r'^user/logout/', 'inboxen.views.login.logout_user'),

    url(r'^email/add/', 'inboxen.views.alias.add_alias'),
    url(r'^email/edit/(?P<email>[a-zA-Z0-9@\.]+)', 'inboxen.views.alias.edit'),
    url(r'^email/delete/(?P<email>[a-zA-Z0-9@\.]+)', 'inboxen.views.alias.confirm_delete'),

    url(r'^inbox/(?P<email_address>[a-zA-Z0-9@\.]+)/view/(?P<emailid>\d+)', 'inboxen.views.inbox.read_email'),
    url(r'^inbox/(?P<email_address>[a-zA-Z0-9@\.]+)(/(?P<page>\d+))?', 'inboxen.views.inbox.inbox'),
    url(r'^email/attachment/(?P<attachment_id>\d+)/(?P<method>\w+)/', 'inboxen.views.inbox.download_attachment'),

    url(r'^inbox/', 'inboxen.views.inbox.inbox'),


   # API stuff.
    #url(r'^api/alias/create', 'inboxen.api.alias_create'),
    #url(r'^api/alias/delete', 'inboxen.api.alias_delete'),
    #url(r'^api/alias', 'inboxen.api.alises'),

    # url(r'^inboxen/', include('inboxen.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)
