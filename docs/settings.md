# Setup anthropic claude with olama
        export ANTHROPIC_BASE_URL="http://192.168.1.36:11434"
        export ANTHROPIC_AUTH_TOKEN="ollama"
        export ANTHROPIC_API_KEY=""

        claude \
        --model qwen2.5:14b \
        --allow-dangerously-skip-permissions \
        --verbose

        sudo claude \
        --model gpt-oss:20b \
        --allow-dangerously-skip-permissions \
        --verbose  

        Create a file hello_world.py that prints "Hello World".

        Open app/app.py and summarize how Neo4j is initialized.


        Create a file test_write.txt that contains exactly this line:

        OK

# Run open-webui
1. docker compose up -d

2. Edit your docker-compose.yml and set:
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"
    environment:
      OLLAMA_BASE_URL: "http://192.168.1.36:11434"
    volumes:
      - open-webui:/app/backend/data


3. Then apply:
docker compose up -d

# 

