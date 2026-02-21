This is really simple GUI for edge-tts. 
Usage is for creation of MP3 files of text files.

Mostly vibe coded with Claude Code website by copy-paste method 😆

### For local run

- Create venv
```
python3 -m venv venv
```

- To install libs
```
pip install -r requirements.txt
```

-  To run locally.
```
python gui
```

### To build (we'll create independent binary file)
```
pyinstaller --onefile --windowed --name "gui-edge-voices" gui.py
```
