# AudioStudio

## Install
Open PowerShell and install python 3.11 by command:
```
winget install --id Python.Python.3.11 -e --source winget
```

Create enviroment:
```
cd .\TTS
py -3.11 -m venv .venv
```

Activate enviroment:
```
.\.venv\Scripts\Activate.ps1
```

Install libraries:
```
python -m pip install --upgrade pip setuptools wheel
# For CPU
pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu

# For GPU
pip install torch==2.6.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

pip install -r requirements.txt
```
