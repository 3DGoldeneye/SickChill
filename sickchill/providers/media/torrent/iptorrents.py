# coding=utf-8
# Author: miigotu <miigotu@gmail.com>
#
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
import traceback

# Third Party Imports
import validators
from requests.compat import urljoin
from requests.utils import dict_from_cookiejar

# First Party Imports
from sickbeard import logger, tvcache
from sickbeard.bs4_parser import BS4Parser
from sickchill.helper.common import convert_size, try_int
from sickchill.providers.media.torrent import TorrentProvider


class IPTorrentsProvider(TorrentProvider):

    def __init__(self):

        super().__init__('IPTorrents', extra_options=('username', 'password', 'minseed', 'minleech', 'custom_url', 'cookies', 'freeleech'))

        self.urls = {'base_url': 'https://iptorrents.eu',
                     'login': 'https://iptorrents.eu/take_login.php',
                     'search': 'https://iptorrents.eu/t?%s%s&q=%s&qf=#torrents'}

        self.url = self.urls['base_url']

        self.categories = '73=&60='

    def login(self):
        cookie_dict = dict_from_cookiejar(self.session.cookies)
        if cookie_dict.get('uid') and cookie_dict.get('pass'):
            return True

        if self.config('cookies'):
            success, status = self.add_cookies_from_ui()
            if not success:
                logger.info(status)
                return False

        login_params = {'username': self.config('username'),
                        'password': self.config('password'),
                        'login': 'submit'}

        if self.config('custom_url'):
            if not validators.url(self.config('custom_url')):
                logger.warning("Invalid custom url: {0}".format(self.config('custom_url')))
                return False

        # Get the index, redirects to login
        data = self.get_url(self.config('custom_url') or self.url, returns='text')
        if not data:
            logger.warning("Unable to connect to provider")
            return False

        with BS4Parser(data, 'html5lib') as html:
            action = html.find('form', {'action': re.compile(r'.*login.*')}).get('action')
            if not action:
                logger.warning('Could not find the login form. Try adding cookies instead')
                return False

        response = self.get_url(urljoin(self.config('custom_url') or self.url, action), post_data=login_params, returns='text')
        if not response:
            logger.warning("Unable to connect to provider")
            return False

        # Invalid username and password combination
        if re.search('Invalid username and password combination', response):
            logger.warning("Invalid username or password. Check your settings")
            return False

        # You tried too often, please try again after 2 hours!
        if re.search('You tried too often', response):
            logger.warning("You tried too often, please try again after 2 hours! Disable IPTorrents for at least 2 hours")
            return False

        # Captcha!
        if re.search('Captcha verification failed.', response):
            logger.warning("Stupid captcha")
            return False

        return True

    def search(self, search_strings, ep_obj=None) -> list:
        results = []
        if not self.login():
            return results

        freeleech = '&free=on' if self.config('freeleech') else ''

        for mode in search_strings:
            items = []
            logger.debug("Search Mode: {0}".format(mode))
            for search_string in search_strings[mode]:
                if mode != 'RSS':
                    logger.debug("Search string: {0}".format(search_string))

                # URL with 50 tv-show results, or max 150 if adjusted in IPTorrents profile
                search_url = self.urls['search'] % (self.categories, freeleech, search_string)
                search_url += ';o=seeders' if mode != 'RSS' else ''

                if self.config('custom_url'):
                    if not validators.url(self.config('custom_url')):
                        logger.warning("Invalid custom url: {0}".format(self.config('custom_url')))
                        return results
                    search_url = urljoin(self.config('custom_url'), search_url.split(self.url)[1])

                data = self.get_url(search_url, returns='text')
                if not data:
                    continue

                try:
                    data = re.sub(r'(?im)<button.+?</button>', '', data, 0)
                    with BS4Parser(data, 'html5lib') as html:
                        if not html:
                            logger.debug("No data returned from provider")
                            continue

                        if html.find(text='No Torrents Found!'):
                            logger.debug("Data returned from provider does not contain any torrents")
                            continue

                        torrent_table = html.find('table', id='torrents')
                        torrents = torrent_table('tr') if torrent_table else []

                        # Continue only if one Release is found
                        if not torrents or len(torrents) < 2:
                            logger.debug("Data returned from provider does not contain any torrents")
                            continue

                        for result in torrents[1:]:
                            try:
                                title = result('td')[1].find('a').text
                                download_url = urljoin(search_url, result('td')[3].find('a')['href'])
                                seeders = int(result.find('td', class_='ac t_seeders').text)
                                leechers = int(result.find('td', class_='ac t_leechers').text)
                                torrent_size = result('td')[5].text
                                size = convert_size(torrent_size) or -1
                            except (AttributeError, TypeError, KeyError):
                                continue

                            if not all([title, download_url]):
                                continue

                            # Filter unseeded torrent
                            if seeders < self.config('minseed') or leechers < self.config('minleech'):
                                if mode != 'RSS':
                                    logger.debug("Discarding torrent because it doesn't meet the minimum seeders or leechers: {0} (S:{1} L:{2})".format
                                               (title, seeders, leechers))
                                continue

                            item = {'title': title, 'link': download_url, 'size': size, 'seeders': seeders, 'leechers': leechers, 'hash': ''}
                            if mode != 'RSS':
                                logger.debug("Found result: {0} with {1} seeders and {2} leechers".format(title, seeders, leechers))

                            items.append(item)

                except Exception as e:
                    logger.exception("Failed parsing provider. Error: {0!r}".format(str(e)))
                    logger.exception(traceback.format_exc())

            # For each search mode sort all the items by seeders if available
            items.sort(key=lambda d: try_int(d.get('seeders', 0)), reverse=True)

            results += items

        return results


