* [ ] Add run time estimation summary after we are done.
* [x] Aspect ratio 4:3 is hard-coded in several places. This should be a command line option, and should default to 16:9
* [ ] Cover info-level debug statements made in the various files with unit tests.
* [x] The tool check at the beginning should check for mkisofs unless the no iso flag is passed.
* [ ] Add file size metrics after each run.
* [ ] After downloading playlist, provide total length of playlist.
* [ ] If the playlist length exceeds the capacity of the DVD, then we want to exclude videos they all fit on the DVD. Warn about this case, and specify all the videos that could not fit on the dvd. Specify both their names and youtube URL.
* [ ] We know exactly what platform we're running on, so cater tool installation messages to the platform. For example, on macos, we don't need to specify linux instructions.
