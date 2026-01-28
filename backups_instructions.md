Here is a Markdown file summarizing the backup instructions for your Neo4j database and InsightViewer files based on your docker-compose.yml setup:

Look for the container name or ID of your Neo4j instance. In your docker-compose.yml, the container name is neo4j.

# Backup Instructions for Neo4j and InsightViewer Files

## 1. Backup Neo4j Database (Docker)

### 1.1 Locate the Neo4j Container
Run the following command to find your Neo4j container:
```bash

docker ps
```

Look for the container name or ID of your Neo4j instance. In your docker-compose.yml, the container name is neo4j.

1.2 Create a Backup
Use the neo4j-admin dump command to create a backup of your database. Replace <container_name> with the name or ID of your Neo4j container:

Create directory if it doesn't exists
```bash
docker exec neo4j mkdir -p /backups
```

Stop the database not the container
```bash
docker exec neo4j neo4j-admin server stop
```

```bash
docker exec neo4j neo4j-admin database dump neo4j --to-path=/backups/neo4j.dump
```

```bash
docker exec neo4j neo4j-admin server start
```

This will create a backup file named neo4j.dump in the /backups directory inside the container.

1.3 Copy the Backup to Your Host Machine
Copy the backup file from the container to your host machine:

```bash
docker cp neo4j:/backups/neo4j.dump /home/robert/backup/neo4j/
```

Replace /path/to/backup/location with the directory on your host machine where you want to store the backup.

2. Backup InsightViewer Files
2.1 Locate the Files
The following directories are mounted from the host machine and should be backed up:

./source/InsightViewer/app/static/editor_files
./source/InsightViewer/app/static/images
./source/InsightViewer
./source/InsightViewer/app/rag/chroma_db
./source/InsightViewer/config.ini

2.2 Create a Backup Archive
Use the tar command to create a compressed archive of the InsightViewer files:

```bash
tar -czvf insightviewer_backup.tar.gz ./source/InsightViewer
```

This will create a file named insightviewer_backup.tar.gz containing all the files in the InsightViewer directory.

3. Automate Backups (Optional)
3.1 Create a Backup Script
Create a script (e.g., backup.sh) to automate the backup process:

```bash
#!/bin/bash

# Backup Neo4j volumes
docker exec neo4j neo4j-admin dump --database=neo4j --to=/backups/neo4j.dump
docker cp neo4j:/backups/neo4j.dump /path/to/backup/location/neo4j_backup_$(date +%Y%m%d).dump

# Backup InsightViewer files
tar -czvf /path/to/backup/location/insightviewer_backup_$(date +%Y%m%d).tar.gz ./source/InsightViewer
```

3.2 Schedule Backups with Cron
Add the script to a cron job to run daily:

```bash
crontab -e
```

Add the following line to schedule the backup at midnight:

```bash
0 0 * * * /path/to/backup.sh
```

4. Verify Backups
4.1 Verify Neo4j Backup
Restore the Neo4j backup in a test environment using:

```bash
docker exec neo4j neo4j-admin load --from=/backups/neo4j.dump --database=neo4j --force
```

4.2 Verify InsightViewer Backup
Extract the .tar.gz file and check the contents:

```bash
tar -xzvf insightviewer_backup.tar.gz -C /path/to/extract/location
```

Ensure all critical files (e.g., database files, HTML files) are included.

5. Notes
Replace /path/to/backup/location with the desired backup directory on your host machine.
Ensure you have sufficient disk space for backups.
Store backups in a secure location, such as an external drive or cloud storage.
