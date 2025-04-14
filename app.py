from datetime import timedelta
import os
import logging
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt, get_jwt_identity
)
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure JWT
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret'  # Change this to a secure key
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=10)

jwt = JWTManager(app)

# Configure PostgreSQL connection
DATABASE_URL = os.environ.get(
    'DATABASE_URL', 'postgres://postgres:postgres@localhost:5432/filmdb')
conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
# Disable autocommit for explicit transaction management.
conn.autocommit = False

###############################
# Login Endpoint
###############################


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
        # For debugging only; remove in production
        logger.info("User from DB: %s", user)
    except Exception as e:
        logger.exception("Error during login")
        return jsonify({"msg": "Internal Server Error"}), 500
    finally:
        cur.close()

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        access_token = create_access_token(
            identity=username, additional_claims={'role': user['role']})
        return jsonify(access_token=access_token)
    else:
        return jsonify({"msg": "Bad username or password"}), 401

###############################
# Protected Admin Example
###############################


@app.route('/admin', methods=['GET'])
@jwt_required()
def admin_dashboard():
    identity = get_jwt_identity()
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403
    return jsonify({"msg": f"Welcome, {identity}! You have admin access."})


@app.route('/public/films', methods=['GET'])
def get_public_films():
    cur = conn.cursor()
    try:
        cur.execute("SELECT film_id, title FROM films WHERE deleted_at IS NULL")
        films = cur.fetchall()
        return jsonify({"films": films})
    except Exception as e:
        logger.exception("Error fetching public films")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films', methods=['GET'])
def get_films():
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM films WHERE deleted_at IS NULL")
        films = cur.fetchall()
        return jsonify({"films": films})
    except Exception as e:
        logger.exception("Error fetching films")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films/<int:film_id>', methods=['GET'])
@jwt_required()
def get_film_details(film_id):
    cur = conn.cursor()
    try:
        # Fetch basic film information, only if not soft-deleted.
        cur.execute(
            "SELECT * FROM films WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        film = cur.fetchone()
        if not film:
            abort(404, description="Film not found")

        # Fetch additional details with deleted_at filter.
        cur.execute(
            "SELECT * FROM film_production_details WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        production_details = cur.fetchone()

        cur.execute(
            "SELECT * FROM film_authors WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        authors = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_production_team WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        production_team = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_actors WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        actors = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_equipment WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        equipment = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_documents WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        documents = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_institutional_info WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
        institutional_info = cur.fetchone()

        cur.execute(
            "SELECT * FROM film_screenings WHERE film_id = %s AND deleted_at IS NULL", (film_id,))
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
        })
    except Exception as e:
        logger.exception("Error fetching film details")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films/full', methods=['GET'])
@jwt_required()
def get_full_film_data():
    try:
        with conn.cursor() as cur:
            query = """
                SELECT
                  f.film_id,
                  f.title,
                  f.release_year,
                  f.runtime,
                  f.synopsis,
                  f.created_at,
                  f.updated_at,

                  pd.production_timeframe,
                  pd.post_production_studio,
                  pd.production_comments,

                  loc.name AS location_name,
                  loc.address AS location_address,
                  loc.city AS location_city,
                  loc.state AS location_state,
                  loc.country AS location_country,
                  loc.latitude AS location_latitude,
                  loc.longitude AS location_longitude,
                  loc.comment AS location_comment,

                  json_agg(DISTINCT jsonb_build_object('role', a.role, 'name', a.name, 'comment', a.comment)) FILTER (WHERE a.author_id IS NOT NULL) AS authors,
                  json_agg(DISTINCT jsonb_build_object('department', t.department, 'name', t.name, 'role', t.role, 'comment', t.comment)) FILTER (WHERE t.team_member_id IS NOT NULL) AS team,
                  json_agg(DISTINCT jsonb_build_object('actor_name', ac.actor_name, 'character_name', ac.character_name, 'comment', ac.comment)) FILTER (WHERE ac.actor_id IS NOT NULL) AS actors,
                  json_agg(DISTINCT jsonb_build_object('equipment_name', eq.equipment_name, 'description', eq.description, 'comment', eq.comment)) FILTER (WHERE eq.equipment_id IS NOT NULL) AS equipment,
                  json_agg(DISTINCT jsonb_build_object('document_type', doc.document_type, 'file_url', doc.file_url, 'comment', doc.comment)) FILTER (WHERE doc.document_id IS NOT NULL) AS documents,
                  json_agg(DISTINCT jsonb_build_object('production_company', info.production_company, 'funding_company', info.funding_company, 'funding_comment', info.funding_comment, 'source', info.source)) FILTER (WHERE info.info_id IS NOT NULL) AS institutional_info,
                  json_agg(DISTINCT jsonb_build_object('screening_date', s.screening_date, 'organizers', s.organizers, 'format', s.format, 'audience', s.audience, 'film_rights', s.film_rights, 'comment', s.comment, 'source', s.source)) FILTER (WHERE s.screening_id IS NOT NULL) AS screenings

                FROM films f
                LEFT JOIN film_production_details pd ON f.film_id = pd.film_id
                LEFT JOIN locations loc ON pd.shooting_location_id = loc.location_id
                LEFT JOIN film_authors a ON f.film_id = a.film_id
                LEFT JOIN film_production_team t ON f.film_id = t.film_id
                LEFT JOIN film_actors ac ON f.film_id = ac.film_id
                LEFT JOIN film_equipment eq ON f.film_id = eq.film_id
                LEFT JOIN film_documents doc ON f.film_id = doc.film_id
                LEFT JOIN film_institutional_info info ON f.film_id = info.film_id
                LEFT JOIN film_screenings s ON f.film_id = s.film_id

                WHERE f.deleted_at IS NULL
                GROUP BY f.film_id, pd.production_detail_id, loc.location_id;
            """
            cur.execute(query)
            films = cur.fetchall()
        return jsonify({"films": films}), 200
    except Exception as e:
        logger.error(f"Error fetching full film data: {e}")
        return jsonify({"error": "Failed to fetch full film data"}), 500


@app.route('/films', methods=['POST'], endpoint='create_film')
@jwt_required()
def create_film():
    # Only allow admin users to add films.
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    film_data = request.get_json()
    if not film_data:
        return jsonify({"msg": "Invalid JSON payload"}), 400

    cur = conn.cursor()
    try:
        # Begin transaction (explicitly starting a transaction is optional here since autocommit is off)
        cur.execute("BEGIN")

        # 1. Insert into films table
        cur.execute("""
            INSERT INTO films (title, release_year, runtime, synopsis)
            VALUES (%s, %s, %s, %s)
            RETURNING film_id
        """, (
            film_data.get('title'),
            film_data.get('release_year'),
            film_data.get('runtime'),
            film_data.get('synopsis')
        ))
        film_id = cur.fetchone()['film_id']

        # 2. Insert into film_production_details table.
        prod = film_data.get('productionDetails', {})
        if prod:
            cur.execute("""
                INSERT INTO film_production_details
                    (film_id, production_timeframe, shooting_location_id,
                     post_production_studio, production_comments)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                film_id,
                prod.get('production_timeframe'),
                prod.get('shooting_location_id'),
                prod.get('post_production_studio'),
                prod.get('production_comments')
            ))

        # 3. Insert into film_authors table.
        authors = film_data.get('authors', {})
        if authors.get('screenwriter'):
            cur.execute("""
                INSERT INTO film_authors (film_id, role, name, comment)
                VALUES (%s, 'Screenwriter', %s, %s)
            """, (film_id, authors.get('screenwriter'), authors.get('screenwriter_comment', '')))
        if authors.get('filmmaker'):
            cur.execute("""
                INSERT INTO film_authors (film_id, role, name, comment)
                VALUES (%s, 'Filmmaker', %s, %s)
            """, (film_id, authors.get('filmmaker'), authors.get('filmmaker_comment', '')))
        if authors.get('executive_producer'):
            cur.execute("""
                INSERT INTO film_authors (film_id, role, name, comment)
                VALUES (%s, 'Executive Producer', %s, %s)
            """, (film_id, authors.get('executive_producer'), authors.get('executive_producer_comment', '')))

        # 4. Insert into film_production_team table.
        production_team = film_data.get('productionTeam', [])
        for member in production_team:
            cur.execute("""
                INSERT INTO film_production_team (film_id, department, name, role, comment)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                film_id,
                member.get('department'),
                member.get('name'),
                member.get('role'),
                member.get('comment')
            ))

        # 5. Insert into film_actors table.
        actors_str = film_data.get('actors', '')
        if actors_str:
            actor_list = [actor.strip()
                          for actor in actors_str.split(',') if actor.strip()]
            for actor in actor_list:
                cur.execute("""
                    INSERT INTO film_actors (film_id, actor_name, character_name, comment)
                    VALUES (%s, %s, NULL, NULL)
                """, (film_id, actor))

        # 6. Insert into film_equipment table.
        equipment = film_data.get('equipment', {})
        if equipment.get('equipment_name'):
            cur.execute("""
                INSERT INTO film_equipment (film_id, equipment_name, description, comment)
                VALUES (%s, %s, %s, %s)
            """, (
                film_id,
                equipment.get('equipment_name'),
                equipment.get('description'),
                equipment.get('comment')
            ))

        # 7. Insert into film_documents table.
        documents = film_data.get('documents', {})
        if documents.get('document_type'):
            cur.execute("""
                INSERT INTO film_documents (film_id, document_type, file_url, comment)
                VALUES (%s, %s, %s, %s)
            """, (
                film_id,
                documents.get('document_type'),
                documents.get('file_url'),
                documents.get('comment')
            ))

        # 8. Insert into film_institutional_info table.
        inst = film_data.get('institutionalInfo', {})
        if inst.get('production_company'):
            cur.execute("""
                INSERT INTO film_institutional_info (film_id, production_company, funding_company, funding_comment, source, funding_location_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                film_id,
                inst.get('production_company'),
                inst.get('funding_company'),
                inst.get('funding_comment'),
                inst.get('source'),
                inst.get('funding_location_id')
            ))

        # 9. Insert into film_screenings table.
        screenings = film_data.get('screenings', [])
        for screening in screenings:
            # only insert if screening_date is provided
            if screening.get('screening_date'):
                cur.execute("""
                    INSERT INTO film_screenings 
                        (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    film_id,
                    screening.get('screening_date'),
                    screening.get('location_id'),
                    screening.get('organizers'),
                    screening.get('format'),
                    screening.get('audience'),
                    screening.get('film_rights'),
                    screening.get('comment'),
                    screening.get('source')
                ))

        conn.commit()
        return jsonify({"film_id": film_id, "msg": "Film created successfully"}), 201
    except Exception as e:
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

    film_data = request.get_json()
    if not film_data:
        return jsonify({"msg": "Invalid JSON payload"}), 400

    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        # 1. Update basic film info.
        cur.execute("""
            UPDATE films
            SET title = %s,
                release_year = %s,
                runtime = %s,
                synopsis = %s,
                updated_at = NOW()
            WHERE film_id = %s
            RETURNING film_id
        """, (
            film_data.get('title'),
            film_data.get('release_year'),
            film_data.get('runtime'),
            film_data.get('synopsis'),
            film_id
        ))
        if cur.rowcount == 0:
            conn.rollback()
            abort(404, description="Film not found")

        # 2. Update production details.
        prod = film_data.get('productionDetails', {})
        cur.execute(
            "DELETE FROM film_production_details WHERE film_id = %s", (film_id,))
        if prod:
            cur.execute("""
                INSERT INTO film_production_details 
                    (film_id, production_timeframe, shooting_location_id, post_production_studio, production_comments)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                film_id,
                prod.get('production_timeframe'),
                prod.get('shooting_location_id'),
                prod.get('post_production_studio'),
                prod.get('production_comments')
            ))

        # 3. Update film authors.
        cur.execute("DELETE FROM film_authors WHERE film_id = %s", (film_id,))
        authors = film_data.get('authors', {})
        if authors.get('screenwriter'):
            cur.execute("""
                INSERT INTO film_authors (film_id, role, name, comment)
                VALUES (%s, 'Screenwriter', %s, %s)
            """, (film_id, authors.get('screenwriter'), authors.get('screenwriter_comment', '')))
        if authors.get('filmmaker'):
            cur.execute("""
                INSERT INTO film_authors (film_id, role, name, comment)
                VALUES (%s, 'Filmmaker', %s, %s)
            """, (film_id, authors.get('filmmaker'), authors.get('filmmaker_comment', '')))
        if authors.get('executive_producer'):
            cur.execute("""
                INSERT INTO film_authors (film_id, role, name, comment)
                VALUES (%s, 'Executive Producer', %s, %s)
            """, (film_id, authors.get('executive_producer'), authors.get('executive_producer_comment', '')))

        # 4. Update production team.
        cur.execute(
            "DELETE FROM film_production_team WHERE film_id = %s", (film_id,))
        production_team = film_data.get('productionTeam', [])
        for member in production_team:
            cur.execute("""
                INSERT INTO film_production_team (film_id, department, name, role, comment)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                film_id,
                member.get('department'),
                member.get('name'),
                member.get('role'),
                member.get('comment')
            ))

        # 5. Update film actors.
        cur.execute("DELETE FROM film_actors WHERE film_id = %s", (film_id,))
        actors_str = film_data.get('actors', '')
        if actors_str:
            actor_list = [a.strip()
                          for a in actors_str.split(',') if a.strip()]
            for actor in actor_list:
                cur.execute("""
                    INSERT INTO film_actors (film_id, actor_name, character_name, comment)
                    VALUES (%s, %s, NULL, NULL)
                """, (film_id, actor))

        # 6. Update film equipment.
        cur.execute("DELETE FROM film_equipment WHERE film_id = %s", (film_id,))
        equipment = film_data.get('equipment', {})
        if equipment.get('equipment_name'):
            cur.execute("""
                INSERT INTO film_equipment (film_id, equipment_name, description, comment)
                VALUES (%s, %s, %s, %s)
            """, (
                film_id,
                equipment.get('equipment_name'),
                equipment.get('description'),
                equipment.get('comment')
            ))

        # 7. Update film documents.
        cur.execute("DELETE FROM film_documents WHERE film_id = %s", (film_id,))
        documents = film_data.get('documents', {})
        if documents.get('document_type'):
            cur.execute("""
                INSERT INTO film_documents (film_id, document_type, file_url, comment)
                VALUES (%s, %s, %s, %s)
            """, (
                film_id,
                documents.get('document_type'),
                documents.get('file_url'),
                documents.get('comment')
            ))

        # 8. Update institutional & financial info.
        cur.execute(
            "DELETE FROM film_institutional_info WHERE film_id = %s", (film_id,))
        inst = film_data.get('institutionalInfo', {})
        if inst.get('production_company'):
            cur.execute("""
                INSERT INTO film_institutional_info (film_id, production_company, funding_company, funding_comment, source, funding_location_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                film_id,
                inst.get('production_company'),
                inst.get('funding_company'),
                inst.get('funding_comment'),
                inst.get('source'),
                inst.get('funding_location_id')
            ))

        # 9. Update film screenings.
        cur.execute(
            "DELETE FROM film_screenings WHERE film_id = %s", (film_id,))
        screenings = film_data.get('screenings', [])
        for screening in screenings:
            if screening.get('screening_date'):
                cur.execute("""
                    INSERT INTO film_screenings 
                        (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    film_id,
                    screening.get('screening_date'),
                    screening.get('location_id'),
                    screening.get('organizers'),
                    screening.get('format'),
                    screening.get('audience'),
                    screening.get('film_rights'),
                    screening.get('comment'),
                    screening.get('source')
                ))

        conn.commit()
        return jsonify({"msg": "Film updated successfully"}), 200
    except Exception as e:
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

        # Soft delete the main film record.
        cur.execute("""
            UPDATE films 
            SET deleted_at = NOW()
            WHERE film_id = %s AND deleted_at IS NULL
            RETURNING film_id
        """, (film_id,))
        if cur.rowcount == 0:
            conn.rollback()
            abort(404, description="Film not found or already deleted")

        # Soft delete dependent records.
        cur.execute(
            "UPDATE film_production_details SET deleted_at = NOW() WHERE film_id = %s", (film_id,))
        cur.execute(
            "UPDATE film_authors SET deleted_at = NOW() WHERE film_id = %s", (film_id,))
        cur.execute(
            "UPDATE film_production_team SET deleted_at = NOW() WHERE film_id = %s", (film_id,))
        cur.execute(
            "UPDATE film_actors SET deleted_at = NOW() WHERE film_id = %s", (film_id,))
        cur.execute(
            "UPDATE film_equipment SET deleted_at = NOW() WHERE film_id = %s", (film_id,))
        cur.execute(
            "UPDATE film_documents SET deleted_at = NOW() WHERE film_id = %s", (film_id,))
        cur.execute(
            "UPDATE film_institutional_info SET deleted_at = NOW() WHERE film_id = %s", (film_id,))
        cur.execute(
            "UPDATE film_screenings SET deleted_at = NOW() WHERE film_id = %s", (film_id,))

        conn.commit()
        return jsonify({"msg": "Film and dependent records soft deleted successfully"}), 200
    except Exception as e:
        conn.rollback()
        logger.exception("Error deleting film")
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


if __name__ == '__main__':
    # In production, set debug=False.
    app.run(port=3001, debug=False)
