from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt, get_jwt_identity
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt

app = Flask(__name__)
CORS(app)

# Configure JWT
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret'  # Change this to a secure key
jwt = JWTManager(app)

# Configure PostgreSQL connection
DATABASE_URL = os.environ.get(
    'DATABASE_URL', 'postgres://postgres:postgres@localhost:5432/filmdb')
conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
conn.autocommit = True

### Login Endpoint ###


@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')

    if not username or not password:
        return jsonify({"msg": "Username and password required"}), 400

    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    print("User from DB:", user)  # For debugging only; remove in production

    cur.close()

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        access_token = create_access_token(
            identity=username, additional_claims={'role': user['role']})
        return jsonify(access_token=access_token)
    else:
        return jsonify({"msg": "Bad username or password"}), 401

### Protected Route Example ###


@app.route('/admin', methods=['GET'])
@jwt_required()
def admin_dashboard():
    identity = get_jwt_identity()
    # Since identity is a string (username), we retrieve the full claims to check role.
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403
    return jsonify({"msg": f"Welcome, {identity}! You have admin access."})

### Existing Film Endpoints ###


@app.route('/films', methods=['GET'])
def get_films():
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM films")
        films = cur.fetchall()
        return jsonify({"films": films})
    except Exception as e:
        print("Error fetching films:", e)
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films/<int:film_id>', methods=['GET'])
@jwt_required()
def get_film_details(film_id):
    cur = conn.cursor()
    try:
        # Fetch basic film information
        cur.execute("SELECT * FROM films WHERE film_id = %s", (film_id,))
        film = cur.fetchone()
        if not film:
            abort(404, description="Film not found")

        # Fetch production details (assuming one row per film)
        cur.execute(
            "SELECT * FROM film_production_details WHERE film_id = %s", (film_id,))
        production_details = cur.fetchone()  # One record expected

        # Fetch film authors (can be multiple)
        cur.execute("SELECT * FROM film_authors WHERE film_id = %s", (film_id,))
        authors = cur.fetchall()

        # Fetch production team (can be multiple)
        cur.execute(
            "SELECT * FROM film_production_team WHERE film_id = %s", (film_id,))
        production_team = cur.fetchall()

        # Fetch film actors (multiple rows)
        cur.execute("SELECT * FROM film_actors WHERE film_id = %s", (film_id,))
        actors = cur.fetchall()

        # Fetch film equipment (multiple rows)
        cur.execute(
            "SELECT * FROM film_equipment WHERE film_id = %s", (film_id,))
        equipment = cur.fetchall()

        # Fetch film documents (multiple rows)
        cur.execute(
            "SELECT * FROM film_documents WHERE film_id = %s", (film_id,))
        documents = cur.fetchall()

        # Fetch institutional & financial info (assuming one row per film)
        cur.execute(
            "SELECT * FROM film_institutional_info WHERE film_id = %s", (film_id,))
        institutional_info = cur.fetchone()

        # Fetch film screenings (can be multiple)
        cur.execute(
            "SELECT * FROM film_screenings WHERE film_id = %s", (film_id,))
        screenings = cur.fetchall()

        # Return a full, unified JSON object with all details
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
        print("Error fetching film details:", e)
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


@app.route('/films', methods=['POST'], endpoint='create_film')
@jwt_required()
def create_film():
    # Ensure only admins can add a film.
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    film_data = request.json
    cur = conn.cursor()
    try:
        # Begin transaction
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
                # must be a valid location id
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
        # Expecting a comma-separated string in film_data['actors']
        actors_str = film_data.get('actors', '')
        if actors_str:
            actor_list = [actor.strip()
                          for actor in actors_str.split(',') if actor.strip()]
            for actor in actor_list:
                # character_name is not provided in our form; insert NULL.
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
                inst.get('funding_location_id')  # must be a valid location id
            ))

        # 9. Insert into film_screenings table.
        screenings = film_data.get('screenings', {})
        if screenings.get('screening_date'):
            cur.execute("""
                INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                film_id,
                screenings.get('screening_date'),
                screenings.get('location_id'),  # must be a valid location id
                screenings.get('organizers'),
                screenings.get('format'),
                screenings.get('audience'),
                screenings.get('film_rights'),
                screenings.get('comment'),
                screenings.get('source')
            ))

        # Commit transaction
        conn.commit()
        return jsonify({"film_id": film_id, "msg": "Film created successfully"}), 201
    except Exception as e:
        conn.rollback()
        print("Error creating film:", e)
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()

##########################
# New Endpoints for Update and Delete
##############################


@app.route('/films/<int:film_id>', methods=['PUT'])
@jwt_required()
def update_film(film_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    film_data = request.json
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")

        # 1. Update films table (basic info)
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

        # 2. Update production details
        prod = film_data.get('productionDetails', {})
        cur.execute("""
            DELETE FROM film_production_details WHERE film_id = %s
        """, (film_id,))
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

        # 3. Update film authors: delete old records and insert new ones.
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

        # 4. Update production team: delete and reinsert.
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

        # 5. Update film actors: delete and reinsert.
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

        # 6. Update film equipment: delete and reinsert.
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

        # 7. Update film documents: delete and reinsert.
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

        # 8. Update institutional & financial info: delete and reinsert.
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

        # 9. Update film screenings: delete and reinsert.
        cur.execute(
            "DELETE FROM film_screenings WHERE film_id = %s", (film_id,))
        screenings = film_data.get('screenings', {})
        if screenings.get('screening_date'):
            cur.execute("""
                INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                film_id,
                screenings.get('screening_date'),
                screenings.get('location_id'),
                screenings.get('organizers'),
                screenings.get('format'),
                screenings.get('audience'),
                screenings.get('film_rights'),
                screenings.get('comment'),
                screenings.get('source')
            ))

        conn.commit()
        return jsonify({"msg": "Film updated successfully"}), 200
    except Exception as e:
        conn.rollback()
        print("Error updating film:", e)
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


# Delete a film – admin only.


@app.route('/films/<int:film_id>', methods=['DELETE'])
@jwt_required()
def delete_film(film_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM films WHERE film_id = %s", (film_id,))
        if cur.rowcount == 0:
            abort(404, description="Film not found")
        return jsonify({"msg": "Film deleted"}), 200
    except Exception as e:
        print("Error deleting film:", e)
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()

##############################
# Public Endpoint (No Authentication)
##############################


@app.route('/public/films', methods=['GET'])
def get_public_films():
    cur = conn.cursor()
    try:
        cur.execute("SELECT film_id, title FROM films")
        films = cur.fetchall()
        return jsonify({"films": films})
    except Exception as e:
        print("Error fetching public films:", e)
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()


if __name__ == '__main__':
    app.run(port=3001, debug=True)
