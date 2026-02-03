# Linux

## nvidia
sudo nvidia-smi
nvtop

## Linux - docker

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
