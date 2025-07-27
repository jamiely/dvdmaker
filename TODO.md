* [x] Add run time estimation summary after we are done.
* [ ] Cover info-level debug statements made in the various files with unit tests.
* [x] Add file size metrics after each run.
* [x] After downloading playlist, provide total length of playlist.
* [x] If the playlist length exceeds the capacity of the DVD, then we want to exclude videos they all fit on the DVD. Warn about this case, and specify all the videos that could not fit on the dvd. Specify both their names and youtube URL.
* [x] We know exactly what platform we're running on, so cater tool installation messages to the platform. For example, on macos, we don't need to specify linux instructions.
* [ ] Document all missing options in README including aspect ratio
* [x] Make duration display human-readable (hours, minutes, seconds instead of just seconds)
* [ ] There are too many INFO level messages (that appear everytime the program is run). Be more selective about what appears by downgrading some messages to DEBUG or TRACE.
