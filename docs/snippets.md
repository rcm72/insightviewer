
# Linux

## venv
source .venv/bin/activate

## nvidia
sudo nvidia-smi
nvtop

## Linux - docker
1. execute in neo4j running in docker
docker exec -it neo4j cypher-shell -u neo4j -p  Sonja1val. "MATCH (s) RETURN count(s)"
2. start and stop docker services
docker compose down
docker compose up
3. start and stop single docker service
docker compose down insightviewer
docker compose up insightviewer
4. what is running
docker ps
5. whatch the logs
docker logs insightviewer


## Ubuntu Network Configuration Guide

This guide provides instructions on how to manage network settings such as IP address configuration, hosts file setup, and retrieving MAC addresses on an Ubuntu system.

### Table of Contents
1. [Changing IP Address](#changing-ip-address)
2. [Setting Up the Hosts File](#setting-up-the-hosts-file)
3. [Finding MAC Addresses](#finding-mac-addresses)

### Changing IP Address

To change the IP address of a network interface in Ubuntu, you can use either manual configuration methods or tools like NetworkManager.

#### Using Netplan (Manual Configuration)
1. **Open Netplan Configuration File:**
   ```bash
   sudo nano /etc/netplan/<your-config-file>

### Setting up the Hosts File
sudo nano /etc/hosts
    192.168.1.5    myserver.example.com    myserver

### Finding MAC addresses
ip link show | grep ether


# Goose
goose session -r --name 20260203_14

# Git
git add .
git commit -m "multiple changes"
git push
git status



# neo4j
1. Unblock
powershell -NoProfile -Command "Get-ChildItem -Recurse 'C:\Work\install\neo4j\neo4j-community-5.26.20-windows\neo4j-community-5.26.20' | Unblock-File"

2. 
set "PATH=C:\Windows\System32\WindowsPowerShell\v1.0\;%PATH%"

where powershell.exe

cd C:\Work\install\neo4j\neo4j-community-5.26.20-windows\neo4j-community-5.26.20>
bin\neo4j.bat console


