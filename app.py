from datetime import timedelta
import os
import logging

from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt, get_jwt_identity
)
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt

# --------------------------------
# App setup
# --------------------------------
app = Flask(__name__)
application = app                # Azure/Gunicorn expects "application"
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------------
# JWT config
# --------------------------------
app.config['JWT_SECRET_KEY'] = os.environ.get(
    'JWT_SECRET_KEY', 'your_jwt_secret')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=10)
jwt = JWTManager(app)

# --------------------------------
# Database connection
# --------------------------------
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgres://postgres:postgres@localhost:5432/filmdb'
)
# allow you to set PGSSLMODE=require in Azure
PGSSLMODE = os.environ.get('PGSSLMODE', 'disable')

conn = psycopg2.connect(
    DATABASE_URL,
    cursor_factory=RealDictCursor,
    sslmode=PGSSLMODE
)
conn.autocommit = False

# --------------------------------
# Endpoints
# --------------------------------


@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')
    if not username or not password:
        return jsonify({"msg": "Username and password required"}), 400

    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        logger.info("User from DB: %s", user)
    except Exception:
        logger.exception("Error during login")
        return jsonify({"msg": "Internal Server Error"}), 500
    finally:
        cur.close()

    if user and bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        token = create_access_token(
            identity=username,
            additional_claims={'role': user['role']}
        )
        return jsonify(access_token=token), 200

    return jsonify({"msg": "Bad username or password"}), 401


@app.route('/admin', methods=['GET'])
@jwt_required()
def admin_dashboard():
    identity = get_jwt_identity()
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403
    return jsonify({"msg": f"Welcome, {identity}! You have admin access."}), 200


@app.route('/public/films', methods=['GET'])
def get_public_films():
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT film_id, title
              FROM films
             WHERE deleted_at IS NULL
        """)
        return jsonify({"films": cur.fetchall()}), 200
    except Exception:
        logger.exception("Error fetching public films")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films', methods=['GET'])
def get_films():
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM films WHERE deleted_at IS NULL")
        return jsonify({"films": cur.fetchall()}), 200
    except Exception:
        logger.exception("Error fetching films")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films/<int:film_id>', methods=['GET'])
@jwt_required()
def get_film_details(film_id):
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT * FROM films WHERE film_id = %s AND deleted_at IS NULL",
            (film_id,)
        )
        film = cur.fetchone()
        if not film:
            abort(404, description="Film not found")

        # production details
        cur.execute("""
            SELECT production_timeframe,
                   post_production_studio,
                   production_comments,
                   shooting_city,
                   shooting_country
              FROM film_production_details
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        production_details = cur.fetchone()

        # authors
        cur.execute("""
            SELECT role, name, comment
              FROM film_authors
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        authors = cur.fetchall()

        # team
        cur.execute("""
            SELECT department, name, role, comment
              FROM film_production_team
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        production_team = cur.fetchall()

        # actors
        cur.execute("""
            SELECT actor_name, character_name, comment
              FROM film_actors
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        actors = cur.fetchall()

        # equipment
        cur.execute("""
            SELECT equipment_name, description, comment
              FROM film_equipment
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        equipment = cur.fetchall()

        # documents
        cur.execute("""
            SELECT document_type, file_url, comment
              FROM film_documents
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        documents = cur.fetchall()

        # institutional info
        cur.execute("""
            SELECT production_company,
                   funding_company,
                   funding_comment,
                   source,
                   institutional_city,
                   institutional_country
              FROM film_institutional_info
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        institutional_info = cur.fetchone()

        # screenings
        cur.execute("""
            SELECT screening_date,
                   screening_city,
                   screening_country,
                   organizers,
                   format,
                   audience,
                   film_rights,
                   comment,
                   source
              FROM film_screenings
             WHERE film_id = %s AND deleted_at IS NULL
        """, (film_id,))
        screenings = cur.fetchall()

        return jsonify({
            "film": film,
            "productionDetails": production_details,
            "authors": authors,
            "productionTeam": production_team,
            "actors": actors,
            "equipment": equipment,
            "documents": documents,
            "institutionalInfo": institutional_info,
            "screenings": screenings
        }), 200

    except Exception:
        logger.exception("Error fetching film details")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films/full', methods=['GET'])
@jwt_required()
def get_full_film_data():
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                  f.film_id,
                  f.title,
                  f.release_year,
                  f.runtime,
                  f.synopsis,
                  f.created_at,
                  f.updated_at,
                  f.av_annotate_link   AS link,
                  pd.production_timeframe,
                  pd.post_production_studio,
                  pd.production_comments,
                  pd.shooting_city      AS production_city,
                  pd.shooting_country   AS production_country,
                  json_agg(DISTINCT jsonb_build_object(
                    'role', a.role,
                    'name', a.name,
                    'comment', a.comment
                  )) FILTER (WHERE a.role IS NOT NULL) AS authors,
                  json_agg(DISTINCT jsonb_build_object(
                    'department', t.department,
                    'name', t.name,
                    'role', t.role,
                    'comment', t.comment
                  )) FILTER (WHERE t.department IS NOT NULL) AS team,
                  json_agg(DISTINCT jsonb_build_object(
                    'actor_name', ac.actor_name,
                    'character_name', ac.character_name,
                    'comment', ac.comment
                  )) FILTER (WHERE ac.actor_name IS NOT NULL) AS actors,
                  json_agg(DISTINCT jsonb_build_object(
                    'equipment_name', eq.equipment_name,
                    'description', eq.description,
                    'comment', eq.comment
                  )) FILTER (WHERE eq.equipment_name IS NOT NULL) AS equipment,
                  json_agg(DISTINCT jsonb_build_object(
                    'document_type', doc.document_type,
                    'file_url', doc.file_url,
                    'comment', doc.comment
                  )) FILTER (WHERE doc.document_type IS NOT NULL) AS documents,
                  json_agg(DISTINCT jsonb_build_object(
                    'production_company', info.production_company,
                    'funding_company', info.funding_company,
                    'funding_comment', info.funding_comment,
                    'source', info.source,
                    'institutional_city', info.institutional_city,
                    'institutional_country', info.institutional_country
                  )) FILTER (WHERE info.production_company IS NOT NULL) AS institutional_info,
                  json_agg(DISTINCT jsonb_build_object(
                    'screening_date', s.screening_date,
                    'screening_city', s.screening_city,
                    'screening_country', s.screening_country,
                    'organizers', s.organizers,
                    'format', s.format,
                    'audience', s.audience,
                    'film_rights', s.film_rights,
                    'comment', s.comment,
                    'source', s.source
                  )) FILTER (WHERE s.screening_date IS NOT NULL) AS screenings,
                  concat(
                    '"', f.title, '". EAC Lab Database. Indiana University Bloomington. ',
                    'Accessed ', TO_CHAR(NOW(), 'DD-MM-YYYY'),
                    '. https://localhost:5001/films'
                  ) AS reference
                FROM films f
                LEFT JOIN film_production_details pd ON f.film_id = pd.film_id
                LEFT JOIN film_authors a             ON f.film_id = a.film_id
                LEFT JOIN film_production_team t     ON f.film_id = t.film_id
                LEFT JOIN film_actors ac             ON f.film_id = ac.film_id
                LEFT JOIN film_equipment eq          ON f.film_id = eq.film_id
                LEFT JOIN film_documents doc         ON f.film_id = doc.film_id
                LEFT JOIN film_institutional_info info ON f.film_id = info.film_id
                LEFT JOIN film_screenings s          ON f.film_id = s.film_id
                WHERE f.deleted_at IS NULL
                GROUP BY f.film_id, pd.production_detail_id
            """)
            films = cur.fetchall()
        return jsonify({"films": films}), 200

    except Exception:
        logger.exception("Error fetching full film data")
        return jsonify({"error": "Failed to fetch full film data"}), 500

# --- Create / Update / Delete film (admin only) ---


@app.route('/films', methods=['POST'])
@jwt_required()
def create_film():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    film_data = request.get_json() or {}
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("""
            INSERT INTO films
              (title, release_year, runtime, synopsis, av_annotate_link)
            VALUES (%s,%s,%s,%s,%s)
            RETURNING film_id
        """, (
            film_data.get('title'),
            film_data.get('release_year'),
            film_data.get('runtime'),
            film_data.get('synopsis'),
            film_data.get('av_annotate_link'),
        ))
        film_id = cur.fetchone()['film_id']

        prod = film_data.get('productionDetails', {})
        cur.execute("""
            INSERT INTO film_production_details
              (film_id, production_timeframe, shooting_city, shooting_country,
               post_production_studio, production_comments)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            film_id,
            prod.get('production_timeframe'),
            prod.get('shooting_city'),
            prod.get('shooting_country'),
            prod.get('post_production_studio'),
            prod.get('production_comments'),
        ))

        for role_key, role_name in [
            ('screenwriter', 'Screenwriter'),
            ('filmmaker', 'Filmmaker'),
            ('executive_producer', 'Executive Producer'),
        ]:
            if film_data.get('authors', {}).get(role_key):
                cur.execute(f"""
                    INSERT INTO film_authors
                      (film_id, role, name, comment)
                    VALUES (%s,%s,%s,%s)
                """, (
                    film_id,
                    role_name,
                    film_data['authors'][role_key],
                    film_data['authors'].get(f"{role_key}_comment", ""),
                ))

        for member in film_data.get('productionTeam', []):
            cur.execute("""
                INSERT INTO film_production_team
                  (film_id, department, name, role, comment)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                film_id,
                member.get('department'),
                member.get('name'),
                member.get('role'),
                member.get('comment'),
            ))

        for name in (film_data.get('actors', '') or '').split(','):
            nm = name.strip()
            if nm:
                cur.execute("""
                    INSERT INTO film_actors
                      (film_id, actor_name, character_name, comment)
                    VALUES (%s,%s,NULL,NULL)
                """, (film_id, nm))

        eq = film_data.get('equipment', {})
        if eq.get('equipment_name'):
            cur.execute("""
                INSERT INTO film_equipment
                  (film_id, equipment_name, description, comment)
                VALUES (%s,%s,%s,%s)
            """, (
                film_id,
                eq.get('equipment_name'),
                eq.get('description'),
                eq.get('comment'),
            ))

        doc = film_data.get('documents', {})
        if doc.get('document_type'):
            cur.execute("""
                INSERT INTO film_documents
                  (film_id, document_type, file_url, comment)
                VALUES (%s,%s,%s,%s)
            """, (
                film_id,
                doc.get('document_type'),
                doc.get('file_url'),
                doc.get('comment'),
            ))

        inst = film_data.get('institutionalInfo', {})
        cur.execute("""
            INSERT INTO film_institutional_info
              (film_id, production_company, funding_company, funding_comment,
               source, institutional_city, institutional_country)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            film_id,
            inst.get('production_company'),
            inst.get('funding_company'),
            inst.get('funding_comment'),
            inst.get('source'),
            inst.get('institutional_city'),
            inst.get('institutional_country'),
        ))

        for s in film_data.get('screenings', []):
            if s.get('screening_date'):
                cur.execute("""
                    INSERT INTO film_screenings
                      (film_id, screening_date, screening_city, screening_country,
                       organizers, format, audience, film_rights, comment, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    film_id,
                    s.get('screening_date'),
                    s.get('screening_city'),
                    s.get('screening_country'),
                    s.get('organizers'),
                    s.get('format'),
                    s.get('audience'),
                    s.get('film_rights'),
                    s.get('comment'),
                    s.get('source'),
                ))

        conn.commit()
        return jsonify({"film_id": film_id, "msg": "Film created successfully"}), 201

    except Exception:
        conn.rollback()
        logger.exception("Error creating film")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films/<int:film_id>', methods=['PUT'])
@jwt_required()
def update_film(film_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    film_data = request.get_json() or {}
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("""
            UPDATE films SET
              title=%s, release_year=%s, runtime=%s,
              synopsis=%s, av_annotate_link=%s, updated_at=NOW()
            WHERE film_id=%s
        """, (
            film_data.get('title'),
            film_data.get('release_year'),
            film_data.get('runtime'),
            film_data.get('synopsis'),
            film_data.get('av_annotate_link'),
            film_id,
        ))
        if cur.rowcount == 0:
            conn.rollback()
            abort(404, description="Film not found")

        cur.execute(
            "DELETE FROM film_production_details WHERE film_id=%s", (film_id,))
        prod = film_data.get('productionDetails', {})
        cur.execute("""
            INSERT INTO film_production_details
              (film_id, production_timeframe, shooting_city, shooting_country,
               post_production_studio, production_comments)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            film_id,
            prod.get('production_timeframe'),
            prod.get('shooting_city'),
            prod.get('shooting_country'),
            prod.get('post_production_studio'),
            prod.get('production_comments'),
        ))

        cur.execute("DELETE FROM film_authors WHERE film_id=%s", (film_id,))
        for key, role in [
            ('screenwriter', 'Screenwriter'),
            ('filmmaker', 'Filmmaker'),
            ('executive_producer', 'Executive Producer')
        ]:
            if film_data.get('authors', {}).get(key):
                cur.execute(f"""
                    INSERT INTO film_authors
                      (film_id, role, name, comment)
                    VALUES (%s,%s,%s,%s)
                """, (
                    film_id,
                    role,
                    film_data['authors'][key],
                    film_data['authors'].get(f"{key}_comment", ""),
                ))

        cur.execute(
            "DELETE FROM film_production_team WHERE film_id=%s", (film_id,))
        for m in film_data.get('productionTeam', []):
            cur.execute("""
                INSERT INTO film_production_team
                  (film_id, department, name, role, comment)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                film_id,
                m.get('department'),
                m.get('name'),
                m.get('role'),
                m.get('comment'),
            ))

        cur.execute("DELETE FROM film_actors WHERE film_id=%s", (film_id,))
        for name in (film_data.get('actors', '') or '').split(','):
            nm = name.strip()
            if nm:
                cur.execute("""
                    INSERT INTO film_actors
                      (film_id, actor_name, character_name, comment)
                    VALUES (%s,%s,NULL,NULL)
                """, (film_id, nm))

        cur.execute("DELETE FROM film_equipment WHERE film_id=%s", (film_id,))
        eq = film_data.get('equipment', {})
        if eq.get('equipment_name'):
            cur.execute("""
                INSERT INTO film_equipment
                  (film_id,equipment_name,description,comment)
                VALUES (%s,%s,%s,%s)
            """, (
                film_id,
                eq.get('equipment_name'),
                eq.get('description'),
                eq.get('comment'),
            ))

        cur.execute("DELETE FROM film_documents WHERE film_id=%s", (film_id,))
        doc = film_data.get('documents', {})
        if doc.get('document_type'):
            cur.execute("""
                INSERT INTO film_documents
                  (film_id,document_type,file_url,comment)
                VALUES (%s,%s,%s,%s)
            """, (
                film_id,
                doc.get('document_type'),
                doc.get('file_url'),
                doc.get('comment'),
            ))

        cur.execute(
            "DELETE FROM film_institutional_info WHERE film_id=%s", (film_id,))
        inst = film_data.get('institutionalInfo', {})
        cur.execute("""
            INSERT INTO film_institutional_info
              (film_id,production_company,funding_company,funding_comment,
               source,institutional_city,institutional_country)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            film_id,
            inst.get('production_company'),
            inst.get('funding_company'),
            inst.get('funding_comment'),
            inst.get('source'),
            inst.get('institutional_city'),
            inst.get('institutional_country'),
        ))

        cur.execute("DELETE FROM film_screenings WHERE film_id=%s", (film_id,))
        for s in film_data.get('screenings', []):
            if s.get('screening_date'):
                cur.execute("""
                    INSERT INTO film_screenings
                      (film_id,screening_date,screening_city,screening_country,
                       organizers,format,audience,film_rights,comment,source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    film_id,
                    s.get('screening_date'),
                    s.get('screening_city'),
                    s.get('screening_country'),
                    s.get('organizers'),
                    s.get('format'),
                    s.get('audience'),
                    s.get('film_rights'),
                    s.get('comment'),
                    s.get('source'),
                ))
        conn.commit()
        return jsonify({"msg": "Film updated successfully"}), 200

    except Exception:
        conn.rollback()
        logger.exception("Error updating film")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films/<int:film_id>', methods=['DELETE'])
@jwt_required()
def delete_film(film_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("""
            UPDATE films SET deleted_at=NOW()
            WHERE film_id=%s AND deleted_at IS NULL
            RETURNING film_id
        """, (film_id,))
        if cur.rowcount == 0:
            conn.rollback()
            abort(404, description="Film not found or already deleted")

        for tbl in [
            'film_production_details', 'film_authors', 'film_production_team',
            'film_actors', 'film_equipment', 'film_documents',
            'film_institutional_info', 'film_screenings'
        ]:
            cur.execute(f"""
                UPDATE {tbl} SET deleted_at=NOW()
                WHERE film_id=%s
            """, (film_id,))
        conn.commit()
        return jsonify({"msg": "Film and dependent records soft deleted"}), 200

    except Exception:
        conn.rollback()
        logger.exception("Error deleting film")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/users', methods=['GET'])
@jwt_required()
def get_users():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT user_id, username, role, created_at
              FROM users
             WHERE deleted_at IS NULL
               AND LOWER(TRIM(role))!='admin'
        """)
        return jsonify({"users": cur.fetchall()}), 200
    except Exception:
        logger.exception("Error fetching users")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/users', methods=['POST'])
@jwt_required()
def add_user():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    data = request.get_json() or {}
    u = data.get('username')
    p = data.get('password')
    if not u or not p:
        return jsonify({"msg": "Username and password are required"}), 400

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT user_id FROM users
             WHERE username=%s AND deleted_at IS NULL
        """, (u,))
        if cur.fetchone():
            return jsonify({"msg": "Username already exists"}), 400

        hash_pw = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
        cur.execute("""
            INSERT INTO users (username,password_hash,role)
            VALUES (%s,%s,%s) RETURNING user_id
        """, (u, hash_pw, 'reader'))
        new_id = cur.fetchone()['user_id']
        conn.commit()
        return jsonify({"user_id": new_id, "msg": "User added successfully"}), 201

    except Exception:
        conn.rollback()
        logger.exception("Error adding user")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_user(user_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403
    data = request.get_json() or {}
    u = data.get('username')
    p = data.get('password')
    if not u or not p:
        return jsonify({"msg": "Username and password are required"}), 400

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT user_id FROM users
             WHERE username=%s AND user_id!=%s AND deleted_at IS NULL
        """, (u, user_id))
        if cur.fetchone():
            return jsonify({"msg": "Username already exists"}), 400

        hash_pw = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
        cur.execute("""
            UPDATE users
               SET username=%s,password_hash=%s
             WHERE user_id=%s AND deleted_at IS NULL
             RETURNING user_id
        """, (u, hash_pw, user_id))
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"msg": "User not found or already deleted"}), 404
        conn.commit()
        return jsonify({"msg": "User updated successfully"}), 200

    except Exception:
        conn.rollback()
        logger.exception("Error updating user")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users SET deleted_at=NOW()
            WHERE user_id=%s AND deleted_at IS NULL
            RETURNING user_id
        """, (user_id,))
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"msg": "User not found or already deleted"}), 404
        conn.commit()
        return jsonify({"msg": "User soft deleted successfully"}), 200

    except Exception:
        conn.rollback()
        logger.exception("Error deleting user")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


# --------------------------------
# Run
# --------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    application.run(host='0.0.0.0', port=port, debug=True)
