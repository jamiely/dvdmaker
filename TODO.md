* [x] Check for a new version if yt-dlp. If there is a new version, replace our current version with that new version.
* [x] Cover info-level logging statements made in the various files with unit tests.
* [x] Increase test coverage (78% → 84%, +93 tests, 336 → 429 total tests)
* [x] We should not check for updated yt-dlp more than once every 24h
* [x] dvdstyler uses spumux to create buttons. we need to do the same. analyze the output in `dvdstyler/dvdstyler.log`. Look up spumux docs. Create a single button that can be pressed to start the dvd. It should correspond to the first button.
* [ ] When I mount the ISO, the name of the DVD is just CDROM. Make it something related to the playlist name.
* [ ] fail if a tool is unavailable.
* [ ] when we check the spumux version, we get too much output. hide that unless DEBUG logging is enabled
      ```
      20:45:33 - WARNING - Command stderr: DVDAuthor::spumux, version 0.7.2.
      Build options: gnugetopt iconv freetype
      Send bug reports to <dvdauthor-users@lists.sourceforge.net>

      INFO: default video format is NTSC
      spumux: unrecognized option `--help'
      WARN: Getopt returned 63
      syntax: spumux [options] script.sub < in.mpg > out.mpg
        -m <mode>   dvd, cvd, or svcd (only the first letter is checked).
          Default is DVD.
        -s <stream> number of the substream to insert (default 0)
        -v <level>  verbosity level (default 0)
        -P          enable progress indicator

        See manpage for config file format.
      ```
