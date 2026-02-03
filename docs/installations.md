## Installing goose (a program like claude for ollama)
1. Download
cd /tmp

Run one of these
1.1 With configuration 
curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | bash

1.2 Without configuration 
curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | CONFIGURE=false bash

2. Now you have to configure goose
goose configure
 Configure proivder / ollama
 add http://192.168.1.36:11434

3. Install extends

3. If goose doesn't return to prompt do:
export GOOSE_MAX_TOKENS=128
export GOOSE_TEMPERATURE=0

4. Check which model is goose using
goose run --provider ollama --model gpt-oss:20b -t "Say hello and tell me which provider and model you are using."
goose info -v


