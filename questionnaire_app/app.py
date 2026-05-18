from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from flask import Flask, jsonify, render_template, request
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable


PROJECT_NAME = os.environ.get("QUESTIONNAIRE_PROJECT", "makeit_questionnaire")
SURVEY_NAME = os.environ.get("QUESTIONNAIRE_SURVEY_NAME", "MakeIT 2026 Audience Knowledge Graph")

# The questionnaire is intentionally data-driven.
# Add/change/remove questions here and questionnaire.html will render them automatically.
# The graph mapping is based on id/type, so changing the label text is safe.
QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "understood",
        "label": "I understood the main idea of using a knowledge graph to connect business and technical knowledge.",
        "type": "rating",
        "required": True,
        "scale_hint": "1 = not at all, 5 = completely",
    },
    {
        "id": "usefulness",
        "label": "The idea seems useful for real business applications.",
        "type": "rating",
        "required": True,
        "scale_hint": "1 = not useful, 5 = very useful",
    },
    {
        "id": "realistic",
        "label": "I think this could realistically be implemented in an organization.",
        "type": "rating",
        "required": True,
        "scale_hint": "1 = not realistic, 5 = very realistic",
    },
    {
        "id": "interest",
        "label": "I would be interested in trying or learning more about such a tool.",
        "type": "rating",
        "required": True,
        "scale_hint": "1 = not interested, 5 = very interested",
    },
    {
        "id": "most_value",
        "label": "Where do you see the most value?",
        "type": "multi_select",
        "required": False,
        "options": [
            "Application dependency analysis",
            "Legacy migration",
            "Business rules documentation",
            "Meeting summaries and decisions",
            "AI search over company knowledge",
            "Impact analysis",
            "Not useful in my context",
        ],
    },
    {
        "id": "role",
        "label": "What is your role?",
        "type": "select",
        "required": False,
        "options": [
            "Developer",
            "Architect",
            "Business analyst",
            "Project manager",
            "Manager",
            "DBA / data engineer",
            "Other",
        ],
    },
    {
        "id": "comment",
        "label": "Any comment, question, or suggestion?",
        "type": "text",
        "required": False,
        "max_length": 1000,
    },
]


def create_app() -> Flask:
    app = Flask(__name__)
    driver = _create_driver()

    @app.get("/")
    def index():
        return render_template(
            "questionnaire.html",
            questions=QUESTIONS,
            survey_name=SURVEY_NAME,
        )

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "projectName": PROJECT_NAME, "survey": SURVEY_NAME})

    @app.post("/submit")
    def submit():
        payload = request.get_json(silent=True) or {}

        # Honeypot field. Real users never fill this; simple bots often do.
        if payload.get("website"):
            return jsonify({"success": True})

        answers, errors = _validate_answers(payload.get("answers") or {})
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        response_id = str(uuid4())
        name = _response_name()
        submitted_at = datetime.now(timezone.utc).isoformat()
        answer_rows = _answer_rows(answers)

        try:
            with driver.session(database=_neo4j_database()) as session:
                session.run(
                    _save_response_cypher(),
                    projectName=PROJECT_NAME,
                    survey_name=SURVEY_NAME,
                    response_name=name,
                    response_id=response_id,
                    submitted_at=submitted_at,
                    user_agent=(request.headers.get("User-Agent") or "")[:300],
                    client_ip=_client_ip()[:80],
                    answers=answer_rows,
                ).single()
        except AuthError:
            app.logger.exception("Neo4j authentication failed while saving questionnaire response.")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Could not save response: Neo4j authentication failed. Check NEO4J_USERNAME and NEO4J_PASSWORD.",
                    }
                ),
                503,
            )
        except ServiceUnavailable:
            app.logger.exception("Neo4j is unavailable while saving questionnaire response.")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Could not save response: Neo4j is unavailable. Check NEO4J_URI and that Neo4j is running.",
                    }
                ),
                503,
            )
        except Neo4jError as exc:
            app.logger.exception("Neo4j error while saving questionnaire response.")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Could not save response because the database rejected the write: {exc.message}",
                    }
                ),
                503,
            )

        return jsonify({"success": True, "name": name})

    @app.get("/admin/stats")
    def stats():
        """Small JSON endpoint that can be useful during the conference."""
        query = """
        MATCH (s:ConferenceSurvey {projectName: $projectName, name: $survey_name})-[:HAS_RESPONSE]->(r:QuestionnaireResponse)
        WITH s, count(r) AS responses
        OPTIONAL MATCH (s)-[:HAS_RESPONSE]->(:QuestionnaireResponse)-[:SEES_VALUE_IN]->(v:ValueArea)
        WITH responses, v.name AS valueArea, count(v) AS count
        ORDER BY count DESC, valueArea
        RETURN responses, collect({name: valueArea, count: count}) AS valueAreas
        """
        try:
            with driver.session(database=_neo4j_database()) as session:
                record = session.run(query, projectName=PROJECT_NAME, survey_name=SURVEY_NAME).single()
            return jsonify(record.data() if record else {"responses": 0, "valueAreas": []})
        except Neo4jError:
            app.logger.exception("Neo4j error while reading stats.")
            return jsonify({"success": False, "error": "Could not read stats."}), 503

    @app.get("/admin/compute-averages")
    def compute_averages():
        """
        Compute rating averages from submitted answers and MERGE QuestionAverage nodes
        linked from the ConferenceSurvey via HAS_QUESTION -> Question -> HAS_AVERAGE.
        Safe to call repeatedly — uses MERGE so it is idempotent.
        """
        rating_ids = [q["id"] for q in QUESTIONS if q.get("type") == "rating"]
        if not rating_ids:
            return jsonify({"success": True, "updated": 0, "message": "No rating questions defined."})

        cypher = """
        MATCH (a:QuestionnaireAnswer)
        WHERE a.projectName = $projectName
          AND a.name IN $rating_ids
          AND a.value IS NOT NULL
          AND trim(toString(a.value)) <> ''
        WITH
          a.name          AS questionId,
          max(a.question) AS questionText,
          avg(toFloat(a.value))          AS averageValue,
          count(a)                       AS responseCount

        MERGE (avgNode:QuestionAverage {projectName: $projectName, questionId: questionId})
        ON CREATE SET avgNode.id_rc = randomUUID(), avgNode.createdAt = datetime()
        SET avgNode.name          = '[' + toString(round(averageValue * 10) / 10.0) + '/5] ' + questionText,
            avgNode.questionText  = questionText,
            avgNode.value         = round(averageValue * 100) / 100.0,
            avgNode.responseCount = responseCount,
            avgNode.updatedAt     = datetime()

        WITH questionId, questionText, avgNode
        MATCH (survey:ConferenceSurvey {projectName: $projectName, name: $survey_name})
        MERGE (q:Question {projectName: $projectName, questionId: questionId})
        ON CREATE SET q.id_rc = randomUUID(), q.createdAt = datetime()
        SET q.name = questionId, q.text = questionText, q.updatedAt = datetime()
        MERGE (survey)-[:HAS_QUESTION]->(q)
        MERGE (q)-[:HAS_AVERAGE]->(avgNode)

        RETURN count(avgNode) AS updated
        """
        try:
            with driver.session(database=_neo4j_database()) as session:
                record = session.run(
                    cypher,
                    projectName=PROJECT_NAME,
                    survey_name=SURVEY_NAME,
                    rating_ids=rating_ids,
                ).single()
            updated = record["updated"] if record else 0
            return jsonify({"success": True, "updated": updated})
        except Neo4jError:
            app.logger.exception("Neo4j error while computing averages.")
            return jsonify({"success": False, "error": "Could not compute averages."}), 503

    @app.post("/admin/constraints")
    def create_constraints():
        token = os.environ.get("QUESTIONNAIRE_ADMIN_TOKEN", "")
        if token and request.headers.get("X-Admin-Token") != token:
            return jsonify({"success": False, "error": "Unauthorized"}), 401

        statements = [
            """
            CREATE CONSTRAINT questionnaire_response_name IF NOT EXISTS
            FOR (r:QuestionnaireResponse) REQUIRE r.name IS UNIQUE
            """,
            """
            CREATE CONSTRAINT questionnaire_answer_name IF NOT EXISTS
            FOR (a:QuestionnaireAnswer) REQUIRE a.name IS UNIQUE
            """,
            """
            CREATE CONSTRAINT questionnaire_question_key IF NOT EXISTS
            FOR (q:Question) REQUIRE (q.projectName, q.questionId) IS UNIQUE
            """,
            """
            CREATE CONSTRAINT conference_survey_key IF NOT EXISTS
            FOR (s:ConferenceSurvey) REQUIRE (s.projectName, s.name) IS UNIQUE
            """,
            """
            CREATE CONSTRAINT value_area_key IF NOT EXISTS
            FOR (v:ValueArea) REQUIRE (v.projectName, v.name) IS UNIQUE
            """,
            """
            CREATE CONSTRAINT obstacle_key IF NOT EXISTS
            FOR (o:Obstacle) REQUIRE (o.projectName, o.name) IS UNIQUE
            """,
            """
            CREATE CONSTRAINT kg_experience_key IF NOT EXISTS
            FOR (e:KnowledgeGraphExperience) REQUIRE (e.projectName, e.name) IS UNIQUE
            """,
            """
            CREATE CONSTRAINT participant_role_key IF NOT EXISTS
            FOR (p:ParticipantRole) REQUIRE (p.projectName, p.name) IS UNIQUE
            """,
            """
            CREATE CONSTRAINT rating_value_key IF NOT EXISTS
            FOR (rv:RatingValue) REQUIRE (rv.projectName, rv.value) IS UNIQUE
            """,
        ]
        with driver.session(database=_neo4j_database()) as session:
            for statement in statements:
                session.run(statement)
        return jsonify({"success": True})

    return app


def _save_response_cypher() -> str:
    return """
    MERGE (survey:ConferenceSurvey {projectName: $projectName, name: $survey_name})
    ON CREATE SET survey.id_rc = randomUUID(), survey.createdAt = datetime()
    SET survey.updatedAt = datetime(),
        survey.title = $survey_name

    CREATE (r:QuestionnaireResponse {
        name: $response_name,
        id_rc: randomUUID(),
        projectName: $projectName,
        responseId: $response_id,
        submittedAt: datetime($submitted_at),
        userAgent: $user_agent,
        clientIp: $client_ip
    })
    MERGE (survey)-[:HAS_RESPONSE]->(r)

    WITH survey, r
    UNWIND $answers AS answer

    MERGE (q:Question {projectName: $projectName, questionId: answer.question_id})
    ON CREATE SET q.id_rc = randomUUID(), q.createdAt = datetime()
    SET q.name = answer.question_id,
        q.text = answer.question,
        q.type = answer.type,
        q.position = answer.position,
        q.required = answer.required,
        q.updatedAt = datetime()
    MERGE (survey)-[:HAS_QUESTION]->(q)

    CREATE (a:QuestionnaireAnswer {
        name: answer.name,
        id_rc: randomUUID(),
        projectName: $projectName,
        questionId: answer.question_id,
        question: answer.question,
        value: answer.value,
        type: answer.type,
        position: answer.position
    })
    CREATE (r)-[:HAS_ANSWER]->(a)
    MERGE (a)-[:ANSWERS_QUESTION]->(q)

    FOREACH (_ IN CASE WHEN answer.type = 'rating' AND answer.value <> '' THEN [1] ELSE [] END |
        MERGE (ratingQuestion:RatingQuestion {projectName: $projectName, questionId: answer.question_id})
        ON CREATE SET ratingQuestion.id_rc = randomUUID(), ratingQuestion.createdAt = datetime()
        SET ratingQuestion.name = answer.question_id,
            ratingQuestion.text = answer.question,
            ratingQuestion.updatedAt = datetime()
        MERGE (survey)-[:HAS_RATING_QUESTION]->(ratingQuestion)
        MERGE (ratingValue:RatingValue {projectName: $projectName, value: toInteger(answer.value)})
        ON CREATE SET ratingValue.id_rc = randomUUID(), ratingValue.createdAt = datetime()
        MERGE (r)-[:RATED {questionId: answer.question_id, question: answer.question}]->(ratingValue)
        MERGE (ratingQuestion)-[:HAS_VALUE]->(ratingValue)
    )

    FOREACH (_ IN CASE WHEN answer.question_id = 'kg_experience' AND answer.value <> '' THEN [1] ELSE [] END |
        MERGE (experience:KnowledgeGraphExperience {projectName: $projectName, name: answer.value})
        ON CREATE SET experience.id_rc = randomUUID(), experience.createdAt = datetime()
        MERGE (survey)-[:HAS_EXPERIENCE_OPTION]->(experience)
        MERGE (r)-[:HAS_KG_EXPERIENCE]->(experience)
    )

    FOREACH (_ IN CASE WHEN answer.question_id = 'role' AND answer.value <> '' THEN [1] ELSE [] END |
        MERGE (role:ParticipantRole {projectName: $projectName, name: answer.value})
        ON CREATE SET role.id_rc = randomUUID(), role.createdAt = datetime()
        MERGE (survey)-[:HAS_ROLE_OPTION]->(role)
        MERGE (r)-[:HAS_ROLE]->(role)
    )

    FOREACH (valueName IN CASE WHEN answer.question_id = 'most_value' AND answer.value <> '' THEN split(answer.value, ', ') ELSE [] END |
        MERGE (valueArea:ValueArea {projectName: $projectName, name: valueName})
        ON CREATE SET valueArea.id_rc = randomUUID(), valueArea.createdAt = datetime()
        MERGE (survey)-[:HAS_VALUE_AREA]->(valueArea)
        MERGE (r)-[:SEES_VALUE_IN]->(valueArea)
    )

    FOREACH (obstacleName IN CASE WHEN answer.question_id = 'obstacles' AND answer.value <> '' THEN split(answer.value, ', ') ELSE [] END |
        MERGE (obstacle:Obstacle {projectName: $projectName, name: obstacleName})
        ON CREATE SET obstacle.id_rc = randomUUID(), obstacle.createdAt = datetime()
        MERGE (survey)-[:HAS_OBSTACLE_OPTION]->(obstacle)
        MERGE (r)-[:SEES_OBSTACLE]->(obstacle)
    )

    FOREACH (_ IN CASE WHEN answer.question_id = 'comment' AND answer.value <> '' THEN [1] ELSE [] END |
        CREATE (comment:QuestionnaireComment {
            name: $response_name + '_comment',
            id_rc: randomUUID(),
            projectName: $projectName,
            text: answer.value,
            createdAt: datetime($submitted_at)
        })
        MERGE (r)-[:HAS_COMMENT]->(comment)
        MERGE (comment)-[:ABOUT_SURVEY]->(survey)
    )

    RETURN DISTINCT r.name AS name
    """


def _create_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    username = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD environment variable is required.")
    return GraphDatabase.driver(uri, auth=(username, password))


def _neo4j_database() -> str | None:
    return os.environ.get("NEO4J_DATABASE") or None


def _response_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{PROJECT_NAME}_response_{stamp}_{uuid4().hex[:8]}"


def _answer_rows(answers: dict[str, str | int]) -> list[dict[str, Any]]:
    rows = []
    for index, question in enumerate(QUESTIONS, start=1):
        rows.append(
            {
                "name": question["id"],
                "question_id": f"{PROJECT_NAME}_answer_{uuid4().hex}",
                "question": question["label"],
                "type": question["type"],
                "required": bool(question.get("required")),
                "value": str(answers.get(question["id"], "")),
                "position": index,
            }
        )
    return rows


def _validate_answers(raw_answers: dict) -> tuple[dict[str, str | int], list[str]]:
    if not isinstance(raw_answers, dict):
        return {}, ["Invalid answers payload."]

    errors: list[str] = []
    answers: dict[str, str | int] = {}

    for question in QUESTIONS:
        question_id = question["id"]
        question_type = question["type"]
        raw_value = raw_answers.get(question_id, "")

        if question_type == "multi_select":
            if isinstance(raw_value, list):
                selected = [str(v).strip() for v in raw_value if str(v).strip()]
            else:
                selected = [v.strip() for v in str(raw_value).split(",") if v.strip()]
            value = ", ".join(selected)
        else:
            value = str(raw_value).strip()

        if question.get("required") and not value:
            errors.append(f"Missing answer: {question['label']}")
            continue

        if not value:
            answers[question_id] = ""
            continue

        if question_type == "rating":
            try:
                rating = int(value)
            except ValueError:
                errors.append(f"Invalid rating: {question['label']}")
                continue
            if rating < 1 or rating > 5:
                errors.append(f"Rating must be from 1 to 5: {question['label']}")
                continue
            answers[question_id] = rating
            continue

        if question_type == "select":
            options = set(question.get("options") or [])
            if value not in options:
                errors.append(f"Invalid option: {question['label']}")
                continue
            answers[question_id] = value
            continue

        if question_type == "multi_select":
            valid_options = set(question.get("options") or [])
            selected = [v.strip() for v in value.split(",") if v.strip()]
            invalid = [v for v in selected if v not in valid_options]
            if invalid:
                errors.append(f"Invalid option(s) for: {question['label']}: {', '.join(invalid)}")
                continue
            answers[question_id] = ", ".join(selected)
            continue

        max_length = int(question.get("max_length") or 500)
        answers[question_id] = value[:max_length]

    return answers, errors


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


app = create_app()
