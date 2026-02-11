# Neo4j + Flask login (2-step) -- security strengthen

## 1) Neo4j: schema + podatkovni model + strengthen security


### Constrainti (enkrat)

``` cypher
CREATE CONSTRAINT user_uid IF NOT EXISTS FOR (u:User) REQUIRE u.id_rc IS UNIQUE;
CREATE CONSTRAINT user_email IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE;
CREATE CONSTRAINT project_name IF NOT EXISTS FOR (p:Project) REQUIRE p.name IS UNIQUE;

CREATE CONSTRAINT role_uid IF NOT EXISTS FOR (u:Role) REQUIRE u.id_rc IS UNIQUE;
CREATE CONSTRAINT role_name IF NOT EXISTS FOR (u:Role) REQUIRE u.name IS UNIQUE;
```

### User model

``` cypher
CREATE (s:User { 
    name:'oglejsi2@gmail.com',
    id_rc: randomUUID(), 
    email: 'oglejsi2@gmail.com',     
    password_hash: "", 
    created_at: timestamp() 
})

```
match(s)
```
create(r:Role) set r.name='admin', r.id_rc=randomUUID() return r;
create(r:Role) set r.name='user', r.id_rc=randomUUID() return r;
```

```
match(u:User) where u.name='oglejsi2@gmail.com' match (r:Role) where r.name='admin' merge(u)-[rel:HAS_ROLE]->(r) return u,rel,r
```

### Membership

``` cypher
match(p:Project) where p.projectName='Zgodovina' match(u:User) where u.name='oglejsi2@gmail.com' merge(u)-[rel:MEMBER_OF]->(p) return p,rel,u
```

------------------------------------------------------------------------

## 2) Seed primer: ustvarimo userja in mu dodelimo projekt

Najprej moraš ustvariti `password_hash` (argon2) v Pythonu (enkrat),
potem ga vpišeš v Neo4j.

### Python (enkrat) -- izpiše hash

``` python
from argon2 import PasswordHasher
ph = PasswordHasher()
print(ph.hash("MojeGeslo123"))
```

Kopiraj izpisani hash.

### Cypher: add password_hast to user

``` cypher
match(u:User) set u.password_hash='$argon2id$v=19$m=65536,t=3,p=4$3p1JhQbdEVgMooSz//s+vg$jedjjoSG50suzO0icu7gqW6bd9t029GJsX4Hql+xBj4' return u
```


------------------------------------------------------------------------

## 3) Flask: varianta A (2-step login)

### (a) helper: argon2 verify + JWT issue

(To imaš lahko v `auth.py`.)

``` python
import os, time, secrets
from jose import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
EXPIRE_SECONDS = 3600

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "Lax")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False

def issue_token(user_uid: str, email: str, project: str, role: str = "user") -> str:
    now = int(time.time())
    payload = {"sub": user_uid, "email": email, "project": project, "role": role,
               "iat": now, "exp": now + EXPIRE_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
```

### (b) repo funkcija: get user + user projects

``` python
def get_user_by_email(email: str):
    with driver.session() as session:
        rec = session.run(
            "MATCH (u:User {email:$email}) RETURN u LIMIT 1",
            email=email
        ).single()
        return dict(rec["u"]) if rec else None

def get_projects_for_user_email(email: str):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {email:$email})-[:MEMBER_OF]->(p:Project)
            RETURN p.name AS name ORDER BY name
        """, email=email)
        return [{"id": r["name"], "name": r["name"]} for r in result]
```

### (c) STEP 1: email+password → vrne projekte

``` python
from flask import request, jsonify

@app.post("/api/login/step1")
def login_step1():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Missing email/password"}), 400

    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Wrong email or password"}), 401

    projects = get_projects_for_user_email(email)
    return jsonify({"projects": projects})
```

### (d) STEP 2: email+password+project → preveri membership → izda cookie

``` python
from flask import make_response
import secrets

@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    project = (data.get("project") or "").strip()

    if not email or not password or not project:
        return jsonify({"error": "Missing email/password/project"}), 400

    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Wrong email or password"}), 401

    # authorization: user mora biti MEMBER_OF tega projekta
    with driver.session() as session:
        ok = session.run("""
            MATCH (u:User {email:$email})-[:MEMBER_OF]->(p:Project {name:$project})
            RETURN count(p) AS c
        """, email=email, project=project).single()["c"] > 0

    if not ok:
        return jsonify({"error": "No access to project"}), 403

    token = issue_token(user_uid=user["uid"], email=email, project=project, role=user.get("role","user"))
    csrf = secrets.token_urlsafe(32)

    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("access_token", token, httponly=True, secure=COOKIE_SECURE,
                    samesite=COOKIE_SAMESITE, path="/")
    resp.set_cookie("csrf_token", csrf, httponly=False, secure=COOKIE_SECURE,
                    samesite=COOKIE_SAMESITE, path="/")
    return resp
```

------------------------------------------------------------------------

## 4) `login.html`: minimalne spremembe (2-step)

### Dodaj password field

``` html
<div style="margin-bottom:12px;">
  <label for="password">Geslo</label>
  <input type="password" id="password" name="password" required placeholder="••••••••">
</div>
```

### Nova submit logika (dvofazno)

``` js
let projectsLoaded = false;

// (koda skrajšana v tem dokumentu – glej originalni vir)
```

------------------------------------------------------------------------

## 5) Zelo pomembno po loginu

-   `/home` naj preveri **JWT cookie**, ne `localStorage`
-   vse endpoint-e filtriraj po **project iz JWT** ali po **uid +
    membership**


## 6) Zagon servisa iz prompta

### 6.1) Get a access_token (parameter i)
```
curl -i -X POST http://192.168.1.16:5001/api/login \
-H "Content-Type: application/json" \
-d '{
  "email": "oglejsi2@gmail.com",
  "password": "Sonja1val.",
  "project": "Zgodovina"
}'
```
### 6.2)  Call run-cypher Get a access_token (parameter i
```
curl -X POST http://192.168.1.16:5001/run-cypher \
-H "Content-Type: application/json" \
-H "Cookie: access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5NWQzYjVlMy00MDljLTRiMjMtOGQwYi1hMjk2MTY2N2IyNWEiLCJlbWFpbCI6Im9nbGVqc2kyQGdtYWlsLmNvbSIsInByb2plY3QiOiJaZ29kb3ZpbmEiLCJyb2xlIjpudWxsLCJpYXQiOjE3NzA0OTM2OTEsImV4cCI6MTc3MDQ5NzI5MX0.7l55uTI4o2VmCDQFVYfU01fwBANMgprlyZ7u_r9s_QI" \
-d '{
  "query": "MATCH (n) RETURN n LIMIT 10",
  "project": "Zgodovina"
}'
```

### 7) Adding security to services
Add these to each service

  # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]    
