# Installing on a Windows machine without Internet access

The trick is to fetch and store every package listed in `requirements.txt`
as a wheel (`.whl`) on a machine that *does* have Internet, then move
that collection to the offline computer and install from it with
`pip --no-index`.

## 1. Prepare the wheel cache on a machine with Internet

1. (Optional) create and activate a venv so you don’t pollute your
   global environment:

   ```powershell
   # choose a directory name and use it consistently; avoid accidental
   # trailing spaces or typos (see note below)
   python -m venv C:\Work\code\rasp_pi\winInstallNoInternet\wheelenv

   # activate it – either from its parent directory…
   cd C:\Work\code\rasp_pi\winInstallNoInternet
   .\wheelenv\Scripts\Activate.ps1

   # …or by calling the script directly
   & C:\Work\code\rasp_pi\winInstallNoInternet\wheelenv\Scripts\Activate.ps1
   ```

2. Update pip/setuptools/wheel:

   ```powershell
   python -m pip install --upgrade pip setuptools wheel
   ```

   > **Tip:** if the machine cannot contact PyPI because of a firewall,
   > proxy or a self‑signed certificate you will see errors like
   > `SSLError … certificate verify failed`.  In that case either install
   > your organisation’s CA into the environment or tell pip to trust the
   > hosts:

   ```powershell
   python -m pip install --upgrade pip setuptools wheel `
       --trusted-host=pypi.org `
       --trusted-host=files.pythonhosted.org
   ```

   It’s perfectly fine to skip this upgrade step entirely; the versions
   that ship with the venv normally build wheels without problems, and a
   failure here does not prevent you from continuing with the rest of
   the procedure.

3. Run `pip wheel` (or `pip download`) against your requirements file:

   ```powershell
   cd <project-root>           # where requirements.txt lives
   pip wheel --wheel-dir=C:\Work\code\rasp_pi\winInstallNoInternet\wheelenv -r requirements.txt
   ```

   or, if you’d rather not build wheels:

   ```powershell
   pip download --dest=C:\Work\code\rasp_pi\winInstallNoInternet -r requirements.txt
   ```

   every dependency (and their dependencies) will be saved as `.whl`
   (or `.tar.gz`) files in `C:\Work\code\rasp_pi\winInstallNoInternet`.

4. Copy the entire wheel directory to the offline machine (USB stick,
   network share, …) – you can keep using the same path on the target if
   you prefer, or drop it somewhere convenient and adjust the
   `--find-links` parameter below.

## 2. Install on the offline Windows machine

1. Place the copied folder somewhere local, e.g. `C:\offline\wheels`.

2. Create/activate the Python environment you want to install into:

   ```powershell
   python -m venv E:\delo\InsightViewer
   E:\delo\InsightViewer\Scripts\activate
   ```

3. Install from the local wheel cache, telling pip not to contact PyPI:

   ```powershell
   pip install --no-index --find-links=C:\offline\wheels -r requirements.txt
   ```

   `--no-index` prevents network access; `--find-links` points pip at
   your local wheel directory.

4. **Copy your application code** to the offline machine as well (USB
   stick, share, …); having the requirements satisfied doesn’t put your
   `.py` files into the venv.

5. Verify the install, e.g. `pip list`, and run your program from the
   location where you copied it, or install the package using
   `pip install -e .` / `pip install .` as described above.

## 3. Additional commands on the remote machine

If you are working from another machine (for example a terminal
connected to the offline host) you can mirror the repository, create
the virtual environment and run the app with a few PowerShell commands.

```powershell
# on the *remote* machine (where InsightViewer lives)
$src = '\\tsclient\C\Work\code\rasp_pi\InsightViewer'
$dst = 'E:\delo\InsightViewer'

robocopy $src $dst /E /XD "$src\.venv"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

# check if E:\delo\InsightViewer\winInstallNoInternet\wheelenv has *.whl files
# if it doesnt that on machine with internet make them and copy to remote machine
cd C:\Work\code\rasp_pi\winInstallNoInternet
pip wheel --wheel-dir=C:\Work\code\rasp_pi\winInstallNoInternet\wheelenv -r requirements.txt

# If files are there then
pip install --no-index --find-links=E:\delo\InsightViewer\winInstallNoInternet\wheelenv -r requirements.txt


# in PowerShell
$env:JWT_SECRET = 'orpnfihG' 
$env:OPENAI_API_KEY= 'no key' 
python .\app\app.py   



echo JAVA_HOME=%JAVA_HOME%
where java
if not "%JAVA_HOME%"=="" "%JAVA_HOME%\bin\java" -version

set "JAVA_HOME=C:\Program Files\Zulu\zulu-21"
set "PATH=%JAVA_HOME%\bin;%PATH%"
java -version
neo4j.bat console
```

## Notes

* Repeat step 1 whenever you change `requirements.txt` (new package or
  version); transfer any new wheels.
* Wheels are platform‑specific when they contain compiled code—you must
  build them on a machine with the same OS/arch as the offline host.
* You can keep the wheel cache in your repo or on a share and update it
  as needed.
* If you cannot reach PyPI at all when preparing the cache (no network,
  corporate firewall, etc.) you do **not** need to upgrade pip before
  running `pip wheel`; simply use the existing venv.  If you do have
  network access but SSL validation fails, see the “Tip” above about
  `--trusted-host` or configuring a CA bundle.

With this workflow you never need Internet on the target machine –
`pip` installs everything from the pre‑downloaded wheels.



# Neo4j APOC export – configuration & usage

This document describes how to configure the Neo4j Docker container so
that `apoc.export.json.query` may write to a file, and how to execute the
export/transfer.

## 1. enable APOC and file exports

The container must have the APOC plugin and the two flags turned on.
add the following environment variables to the `neo4j` service in
`docker‑compose.yml`:

```yaml
services:
  neo4j:
    image: neo4j:5.25-community
    …
    environment:
      # …existing entries…
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_security_procedures_unrestricted: "apoc.*"
      NEO4J_dbms_security_procedures_allowlist: "apoc.*"

      # enable export/import to the filesystem
      NEO4J_apoc_export_file_enabled: "true"
      NEO4J_apoc_import_file_enabled: "true"

      # (other settings such as memory, auth, etc.)
```

make sure the import directory is mounted so you can read the file later:

```yaml
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_plugins:/plugins
      - neo4j_import:/var/lib/neo4j/import
```

> **Note:** the variable names are case‑sensitive; do **not** use
> `NEO4J_APOC_EXPORT_FILE_ENABLED` etc., they produce an invalid
> config key and Neo4j will fail to start.

## 2. restart the container

```sh
cd /home/robert/insightViewer
docker-compose down
docker-compose up -d neo4j    # or `docker-compose up -d --force-recreate neo4j`
```

check the setting from inside the running container:

```sh
docker exec -it neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  'SHOW SETTINGS WHERE name="apoc.export.file.enabled";'
# should return value=true
```

## 3. run the export query

execute your Cypher on the source database:

```cypher
MATCH (s:User)
WHERE NOT ANY(l IN labels(s) WHERE toLower(l) CONTAINS 'custom')
  AND NOT 'NodeType' IN labels(s)
OPTIONAL MATCH (s)-[r]-(t)
WITH
  collect(DISTINCT s) + collect(DISTINCT t) AS ns,
  collect(DISTINCT r) AS rs
WITH
  [n IN ns WHERE n IS NOT NULL] AS nodeList,
  [rel IN rs WHERE rel IS NOT NULL] AS relList
CALL apoc.export.json.data(nodeList, relList, "transfer.json", {jsonFormat:"JSON_LINES"})
YIELD file, nodes AS exportedNodes, relationships AS exportedRels, properties
RETURN file, exportedNodes, exportedRels, properties;
```

the procedure writes `transfer.json` to the import folder inside the
container (`/var/lib/neo4j/import/transfer.json`, i.e. the `neo4j_import`
volume on the host). copy it out with:

```sh
sudo docker cp neo4j:/var/lib/neo4j/import/transfer.json ./transfer.json
# –or– look in the mounted directory on the host
```

## 4. move and import on destination

transfer the file to the other machine (scp/rsync, …) and then run on the
destination Neo4j instance:

```cypher
CALL apoc.import.json(
  'file:///transfer.json',
  {readLabels:true, readRels:true, storeNodeIds:true}
) YIELD file, nodes, relationships;
```

You might get some unique constraint warnings

## 5. streaming alternative

If you cannot or do not wish to write files from the source container,
use the streaming option and handle the JSON in your client:

```cypher
CALL apoc.export.json.query(
  "…same query…",
  null,
  {stream:true, useTypes:true}
) YIELD data
RETURN data;
```

`data` is a single large string; save it locally, copy it to the
destination and import with `apoc.import.json` as shown above.

## 6. Installing apoc on windows

The import procedure (`apoc.import.json`) only exists when the APOC
plugin is present and enabled.  On your Windows box you already
downloaded a set of jars from the APOC release; you only need one of
them, the one that matches the Neo4j version you are running.

1. **check the Neo4j version** on the destination (browser or
   `neo4j.bat`):

   ```cypher
   RETURN dbms.components()[0].versions[0] AS neo4jVersion;
   ```

2. Pick the corresponding jar from your list.  For Neo4j 5.x the usual
   choice is the “extended” build, e.g. 
   The plain apoc-2026.01.4-core.jar.

3. Copy that jar into the plugins directory of the Windows installation,
   e.g.

   ```
   C:\Program Files\Neo4j\neo4j-community\plugins\apoc-2026.01.0-extended.jar
   ```

4. Edit/create conf\apoc.conf  and add/ensure the following lines are present:

   ```properties
      dbms.security.procedures.unrestricted=apoc.*
      dbms.security.procedures.allowlist=apoc.*
      apoc.import.file.enabled=true
      apoc.export.file.enabled=true      # not needed for import, but harmless
   ```

5. Restart Neo4j (`neo4j.bat stop`/`start` or restart the Windows
   service).

6. Verify APOC is loaded:

   ```cypher
      SHOW PROCEDURES
      YIELD name, signature
      WHERE name CONTAINS 'dbms' OR name CONTAINS 'apoc'
      RETURN name, signature
      ORDER BY name
      LIMIT 20;
   ```

   `apoc.import.json` should now appear.  You can then copy
   `transfer.json` into the server’s import folder and run the import
   command shown earlier.

> **Tip:** when you upgrade Neo4j, download the matching APOC jar and
> replace the old one – mismatched versions will prevent the server from
> starting.

---

Following these steps you can configure the Dockerised Neo4j instance and
run `apoc.export.json.query` to produce a file suitable for transfer and
re‑import on another machine.

## 7. Installing server waitress 

