# usage by directory
du -sh */ 2>/dev/null

# hiden directory usage
du -sh .*

# clean up venv
```
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # Ensure your requirements
```

# run insightviwere
```
python -m venv venv
Linux : source venv/bin/activate   
Windows: .\venv\Scripts\activate

Linux
$env:JWT_SECRET="orpnfihG"
$env:OPENAI_API_KEY="your-openai-key"

Windows 
set JWT_SECRET=something
set OPENAI_API_KEY=your-openai-key



# install everything from requirements.txt; uvloop is conditional so
# on Windows it will be skipped automatically (that’s what caused the
# build‑wheel error you saw).
pip install -r requirements.txt

# the preceding command only installs *libraries* – it does not copy
# or register your own application code. make sure the repo is present
# in the environment (copy it from your workstation if you’re offline)
# and either run the script directly…
python app/app.py

# …or, if you have a proper package layout, install the project itself:
#   cd /path/to/insightViewer
#   pip install -e .          # editable install during development
#   pip install .              # build a wheel and install
```
