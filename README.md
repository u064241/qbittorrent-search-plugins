# qBittorrent-search-plugins

Search engines for [qBittorrent](https://www.qbittorrent.org/):

- Academic Torrents
- bt4g
- bt.etree.org
- BTmulu
- ETTV
- GloTorrents
- Il Corsaro Nero
- Kickass Torrent
- MagnetDL
- Mejor Torrent
- Nyaa.si
- OxTorrent
- RockBox
- Rutor
- Snowfl
- Sub Torrents
- Tokyo Toshokan
- TorrentFunk
- TorrentProject
- UnionDHT
- YourBittorrent
- Yts.am


## Notes

If the `Download` button doesn't work you can try to browse the website using the `Open description page` option instead.


## Installation

1. Enable the Search tab by:

`View` > `Search Engine`.

2. Install the plugins by:

`Search` > `Search plugins...` > `Install new one` > Select all the `*.py` files > click `Open`.


### Automatic install

`install_plugins.py` tests each plugin's site for reachability and copies the
reachable ones straight into qBittorrent's engine directory (auto-detected on
Windows / macOS / Linux). Cloudflare `52x` (origin down) counts as unreachable.

```sh
# Fetch from this repo and install the reachable plugins:
python install_plugins.py --repo u064241/qbittorrent-search-plugins

# ...or from a local checkout:
python install_plugins.py --src .

python install_plugins.py --dry-run   # report only, copy nothing
python install_plugins.py --all       # install every plugin, skip the test
```

Restart qBittorrent (or `Search` > `Search plugins...` > `Check for updates`)
to load them.


## Credits


