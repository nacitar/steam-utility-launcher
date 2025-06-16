# Steam Utility Launcher
Downloads utilities from github releases and runs them.  On linux, it will run
them within the same proton prefix that the game uses so that trainers and
practice tools will function properly.  On windows, it simply runs the
applications directly.


# Setup
Simply clone this repository, go to its root and execute:
```
poetry install
```

# Examples
NOTE: _ALWAYS_ run the utilities AFTER opening the game first!

## Manual Usage
If you want to use DSR-Gadget with Dark Souls: Remastered
```
poetry run app -g 570940 /path/to/DSR-Gadget.exe
```

## Builtin Utilities
After running Dark Souls: Remastered, you can launch DSR-Gadget:
```
poetry run app dsr-gadget
```

After running Hitman WoA, you can launch Peacock:
```
poetry run app hitman-peacock
```
