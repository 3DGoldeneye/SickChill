# coding=utf-8
# Author: Dustyn Gibson <miigotu@gmail.com>
# URL: https://sickchill.github.io
#
# This file is part of SickChill.
#
# SickChill is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickChill is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickChill. If not, see <http://www.gnu.org/licenses/>.
# Stdlib Imports
import re

# First Party Imports
import sickbeard
from sickbeard import common, logger
from sickbeard.helpers import getURL, make_session

try:
    # Stdlib Imports
    from xml.etree import cElementTree as etree
except ImportError:
    # Stdlib Imports
    from xml.etree import ElementTree as etree

# Local Folder Imports
# Local Folder Imports
from .base import AbstractNotifier


class Notifier(AbstractNotifier):
    def __init__(self):
        super().__init__('Plex', extra_options=('update_library', 'server_https'))
        self.headers = {
            'X-Plex-Device-Name': 'SickChill',
            'X-Plex-Product': 'SickChill Notifier',
            'X-Plex-Client-Identifier': sickbeard.common.USER_AGENT,
            'X-Plex-Version': '2016.02.10'
        }
        self.session = make_session()

    def _notify_pht(self, message, title='SickChill', host=None, username=None, password=None, force=False):
        """Internal wrapper for the notify_snatch and notify_download functions

        Args:
            message: Message body of the notice to send
            title: Title of the notice to send
            host: Plex Home Theater(s) host:port
            username: Plex username
            password: Plex password
            force: Used for the Test method to override config safety checks

        Returns:
            Returns a list results in the format of host:ip:result
            The result will either be 'OK' or False, this is used to be parsed by the calling function.

        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not self.config('enabled') and not force:
            return False

        host = host or sickbeard.PLEX_CLIENT_HOST
        username = username or sickbeard.PLEX_CLIENT_USERNAME
        password = password or sickbeard.PLEX_CLIENT_PASSWORD

        return sickbeard.notifiers.kodi_notifier._notify_kodi(message, title=title, host=host, username=username, password=password, force=force, dest_app="PLEX")

##############################################################################
# Public functions
##############################################################################

    def notify_snatch(self, name):
        if self.config('snatch'):
            self._notify_pht(name, common.notifyStrings[common.NOTIFY_SNATCH])

    def notify_download(self, name):
        if self.config('download'):
            self._notify_pht(name, common.notifyStrings[common.NOTIFY_DOWNLOAD])

    def notify_subtitle_download(self, name, lang):
        if self.config('subtitle'):
            self._notify_pht(name + ': ' + lang, common.notifyStrings[common.NOTIFY_SUBTITLE_DOWNLOAD])

    def notify_git_update(self, new_version='??'):
        if self.config('update'):
            update_text = common.notifyStrings[common.NOTIFY_GIT_UPDATE_TEXT]
            title = common.notifyStrings[common.NOTIFY_GIT_UPDATE]
            if update_text and title and new_version:
                self._notify_pht(update_text + new_version, title)

    def notify_login(self, ipaddress=""):
        if self.config('login'):
            update_text = common.notifyStrings[common.NOTIFY_LOGIN_TEXT]
            title = common.notifyStrings[common.NOTIFY_LOGIN]
            if update_text and title and ipaddress:
                self._notify_pht(update_text.format(ipaddress), title)

    def test_notify_pht(self, host, username, password):
        return self._notify_pht('This is a test notification from SickChill',
                                'Test Notification', host, username, password, force=True)

    def test_notify_pms(self, host, username, password, plex_server_token):
        return self.update_library(host=host, username=username, password=password,
                                   plex_server_token=plex_server_token, force=True)

    def update_library(self, ep_obj=None, host=None,
                       username=None, password=None,
                       plex_server_token=None, force=False):

        """Handles updating the Plex Media Server host via HTTP API

        Plex Media Server currently only supports updating the whole video library and not a specific path.

        Returns:
            Returns None for no issue, else a string of host with connection issues

        """

        if not (self.config('server_enabled') and self.config('server_update_library')) and not force:
            return None

        host = host or self.config('server_host')
        if not host:
            logger.debug('PLEX: No Plex Media Server host specified, check your settings')
            return False

        if not self.get_token(username, password, plex_server_token):
            logger.warning('PLEX: Error getting auth token for Plex Media Server, check your settings')
            return False

        file_location = '' if not ep_obj else ep_obj.location
        host_list = {x.strip() for x in host.split(',') if x.strip()}
        hosts_all = hosts_match = {}
        hosts_failed = set()

        for cur_host in host_list:

            url = 'http{0}://{1}/library/sections'.format(('', 's')[sickbeard.PLEX_SERVER_HTTPS], cur_host)
            try:
                xml_response = getURL(url, headers=self.headers, session=self.session, returns='text', verify=False,
                                      allow_proxy=False)
                if not xml_response:
                    logger.warning('PLEX: Error while trying to contact Plex Media Server: {0}'.format
                               (cur_host))
                    hosts_failed.add(cur_host)
                    continue

                media_container = etree.fromstring(xml_response)
            except IOError as error:
                logger.warning('PLEX: Error while trying to contact Plex Media Server: {0}'.format
                           (str(error)))
                hosts_failed.add(cur_host)
                continue
            except Exception as error:
                if 'invalid token' in str(error):
                    logger.warning('PLEX: Please set TOKEN in Plex settings: ')
                else:
                    logger.warning('PLEX: Error while trying to contact Plex Media Server: {0}'.format
                               (str(error)))
                hosts_failed.add(cur_host)
                continue

            sections = media_container.findall('.//Directory')
            if not sections:
                logger.debug('PLEX: Plex Media Server not running on: {0}'.format
                           (cur_host))
                hosts_failed.add(cur_host)
                continue

            for section in sections:
                if 'show' == section.attrib['type']:

                    keyed_host = [(str(section.attrib['key']), cur_host)]
                    hosts_all.update(keyed_host)
                    if not file_location:
                        continue

                    for section_location in section.findall('.//Location'):
                        section_path = re.sub(r'[/\\]+', '/', section_location.attrib['path'].lower())
                        section_path = re.sub(r'^(.{,2})[/\\]', '', section_path)
                        location_path = re.sub(r'[/\\]+', '/', file_location.lower())
                        location_path = re.sub(r'^(.{,2})[/\\]', '', location_path)

                        if section_path in location_path:
                            hosts_match.update(keyed_host)

        if force:
            return (', '.join(set(hosts_failed)), None)[not len(hosts_failed)]

        if hosts_match:
            logger.debug('PLEX: Updating hosts where TV section paths match the downloaded show: ' + ', '.join(set(hosts_match)))
        else:
            logger.debug('PLEX: Updating all hosts with TV sections: ' + ', '.join(set(hosts_all)))

        hosts_try = (hosts_match.copy(), hosts_all.copy())[not len(hosts_match)]
        for section_key, cur_host in hosts_try.items():

            url = 'http{0}://{1}/library/sections/{2}/refresh'.format(('', 's')[sickbeard.PLEX_SERVER_HTTPS], cur_host, section_key)
            try:
                getURL(url, headers=self.headers, session=self.session, returns='text', verify=False, allow_proxy=False)
            except Exception as error:
                logger.warning('PLEX: Error updating library section for Plex Media Server: {0}'.format
                           (str(error)))
                hosts_failed.add(cur_host)

        return (', '.join(set(hosts_failed)), None)[not len(hosts_failed)]

    def get_token(self, username=None, password=None, plex_server_token=None):
        username = username or sickbeard.PLEX_SERVER_USERNAME
        password = password or sickbeard.PLEX_SERVER_PASSWORD
        plex_server_token = plex_server_token or sickbeard.PLEX_SERVER_TOKEN

        if plex_server_token:
            self.headers['X-Plex-Token'] = plex_server_token

        if 'X-Plex-Token' in self.headers:
            return True

        if not (username and password):
            return True

        logger.debug('PLEX: fetching plex.tv credentials for user: ' + username)

        params = {
            'user[login]': username,
            'user[password]': password
        }

        try:
            response = getURL('https://plex.tv/users/sign_in.json',
                              post_data=params,
                              headers=self.headers,
                              session=self.session,
                              returns='json',
                              allow_proxy=False)

            self.headers['X-Plex-Token'] = response['user']['authentication_token']

        except Exception as error:
            self.headers.pop('X-Plex-Token', '')
            logger.debug('PLEX: Error fetching credentials from from plex.tv for user {0}: {1}'.format
                       (username, error))

        return 'X-Plex-Token' in self.headers