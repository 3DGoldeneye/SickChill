# coding=utf-8
# Author: Dustyn Gibson <miigotu@gmail.com>
# URL: https://sickchill.github.io
#
# This file is part of SickChill.
#
# SickChill is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Fre$
# Foundation, either version 3 of the License, or (at your option) any later version.
#
# SickChill is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or$
# PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with SickChill. If not, see <http://www.gnu.org/licenses/>.
# Stdlib Imports
import json
import re

# First Party Imports
from sickbeard import logger, tvcache
from sickchill.helper.common import convert_size, try_int
from sickchill.providers.media.torrent import TorrentProvider


class NcoreProvider(TorrentProvider):

    def __init__(self):

        super().__init__('ncore.cc', extra_options=('username', 'password', 'minseed', 'minleech'))

        categories = [
            'xvidser_hun', 'xvidser',
            'dvdser_hun', 'dvdser',
            'hdser_hun', 'hdser'
        ]
        categories = '&kivalasztott_tipus=' + ','.join([x for x in categories])

        self.url = 'https://ncore.cc/'
        self.urls = {
            'login': 'https://ncore.cc/login.php',
            'search': ('https://ncore.cc/torrents.php?nyit_sorozat_resz=true&{cats}&mire=%s&miben=name'
                       '&tipus=kivalasztottak_kozott&submit.x=0&submit.y=0&submit=Ok'
                       '&tags=&searchedfrompotato=true&jsons=true').format(cats=categories)
        }

    def login(self):

        login_params = {
            'nev': self.config('username'),
            'pass': self.config('password'),
            'submitted': '1',
        }

        response = self.get_url(self.urls["login"], post_data=login_params, returns="text")
        if not response:
            logger.warning("Unable to connect to provider")
            return False

        if re.search('images/warning.png', response):
            logger.warning("Invalid username or password. Check your settings")
            return False

        return True

    def search(self, search_strings, ep_obj=None) -> list:
        results = []
        if not self.login():
            return results

        for mode in search_strings:
            items = []
            logger.debug("Search Mode: {0}".format(mode))

            for search_string in search_strings[mode]:
                if mode != "RSS":
                    logger.debug("Search string: {0}".format(search_string))

                url = self.urls['search'] % (search_string)
                data = self.get_url(url, returns="text")

                try:
                  parsed_json = json.loads(data)
                except ValueError as e:
                  continue

                if not isinstance(parsed_json, dict):
                    logger.debug("No data returned from provider")
                    continue

                torrent_results = parsed_json['total_results']

                if not torrent_results:
                    logger.debug("Data returned from provider does not contain any torrents")
                    continue

                logger.info('Number of torrents found on nCore = ' + str(torrent_results))

                for item in parsed_json['results']:
                    try:
                        title = item.pop("release_name")
                        download_url = item.pop("download_url")
                        if not all([title, download_url]):
                            continue

                        seeders = item.pop("seeders")
                        leechers = item.pop("leechers")

                        if seeders < self.config('minseed') or leechers < self.config('minleech'):
                            if mode != "RSS":
                                logger.debug("Discarding torrent because it doesn't meet the minimum seeders or leechers: {0} (S:{1} L:{2})".format(title, seeders, leechers))
                            continue

                        torrent_size = item.pop("size", -1)
                        size = convert_size(torrent_size) or -1

                        if mode != "RSS":
                            logger.debug("Found result: {0} with {1} seeders and {2} leechers with a file size {3}".format(title, seeders, leechers, size))

                        result = {'title': title, 'link': download_url, 'size': size, 'seeders': seeders, 'leechers': leechers, 'hash': ''}
                        items.append(result)

                    except Exception:
                        continue

            # For each search mode sort all the items by seeders
            items.sort(key=lambda d: try_int(d.get('seeders', 0)), reverse=True)
            results += items
        return results

