# coding=utf-8
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
import json

# Third Party Imports
from requests.compat import urlencode

# First Party Imports
from sickbeard import logger, tvcache
from sickchill.helper.common import convert_size, try_int
from sickchill.helper.exceptions import AuthException
from sickchill.providers.media.torrent import TorrentProvider


class NorbitsProvider(TorrentProvider):
    """Main provider object"""

    def __init__(self):
        """ Initialize the class """
        super().__init__('Norbits', extra_options=('username', 'passkey', 'minseed', 'minleech'))

        self.min_cache_time = 20

        self.url = 'https://norbits.net'
        self.urls = {'search': self.url + '/api2.php?action=torrents',
                     'download': self.url + '/download.php?'}

    def _check_auth(self):

        if not self.config('username') or not self.config('passkey'):
            raise AuthException(('Your authentication credentials for {} are '
                                 'missing, check your config.').format(self.name))

        return True

    @staticmethod
    def _check_auth_from_data(parsed_json):
        """ Check that we are authenticated. """

        if 'status' in parsed_json and 'message' in parsed_json and parsed_json.get('status') == 3:
            logger.warning('Invalid username or password. Check your settings')

        return True

    def search(self, search_strings, ep_obj=None) -> list:
        """ Do the actual searching and JSON parsing"""

        results = []

        for mode in search_strings:
            items = []
            logger.debug('Search Mode: {0}'.format(mode))

            for search_string in search_strings[mode]:
                if mode != 'RSS':
                    logger.debug('Search string: {0}'.format(search_string))

                post_data = {
                    'username': self.config('username'),
                    'passkey': self.config('passkey'),
                    'category': '2',  # TV Category
                    'search': search_string,
                }

                self._check_auth()
                parsed_json = self.get_url(self.urls['search'],
                                           post_data=json.dumps(post_data),
                                           returns='json')

                if not parsed_json:
                    return results

                if self._check_auth_from_data(parsed_json):
                    json_items = parsed_json.get('data', '')
                    if not json_items:
                        logger.exception('Resulting JSON from provider is not correct, not parsing it')

                    for item in json_items.get('torrents', []):
                        title = item.pop('name', '')
                        download_url = '{0}{1}'.format(
                            self.urls['download'],
                            urlencode({'id': item.pop('id', ''), 'passkey': self.config('passkey')}))

                        if not all([title, download_url]):
                            continue

                        seeders = try_int(item.pop('seeders', 0))
                        leechers = try_int(item.pop('leechers', 0))

                        if seeders < self.config('minseed') or leechers < self.config('minleech'):
                            logger.debug('Discarding torrent because it does not meet the minimum seeders or leechers: {0} (S:{1} L:{2})'.format(title, seeders, leechers))
                            continue

                        info_hash = item.pop('info_hash', '')
                        size = convert_size(item.pop('size', -1), -1)

                        item = {'title': title, 'link': download_url, 'size': size, 'seeders': seeders, 'leechers': leechers, 'hash': info_hash}
                        if mode != 'RSS':
                            logger.debug('Found result: {0} with {1} seeders and {2} leechers'.format(title, seeders, leechers))

                        items.append(item)
            # For each search mode sort all the items by seeders if available
            items.sort(key=lambda d: try_int(d.get('seeders', 0)), reverse=True)

            results += items

        return results