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
        cur.execute("SELECT * FROM films WHERE film_id = %s", (film_id,))
        film = cur.fetchone()
        if not film:
            abort(404, description="Film not found")

        # Fetch related details
        cur.execute(
            "SELECT * FROM film_production_details WHERE film_id = %s", (film_id,))
        production_details = cur.fetchall()

        cur.execute("SELECT * FROM film_authors WHERE film_id = %s", (film_id,))
        authors = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_production_team WHERE film_id = %s", (film_id,))
        production_team = cur.fetchall()

        cur.execute("SELECT * FROM film_actors WHERE film_id = %s", (film_id,))
        actors = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_equipment WHERE film_id = %s", (film_id,))
        equipment = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_documents WHERE film_id = %s", (film_id,))
        documents = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_institutional_info WHERE film_id = %s", (film_id,))
        institutional_info = cur.fetchall()

        cur.execute(
            "SELECT * FROM film_screenings WHERE film_id = %s", (film_id,))
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
        cur.execute("""
            INSERT INTO films (title, release_year, runtime, synopsis)
            VALUES (%s, %s, %s, %s)
            RETURNING film_id, title, release_year, runtime, synopsis
        """, (
            film_data.get('title'),
            film_data.get('release_year'),
            film_data.get('runtime'),
            film_data.get('synopsis')
        ))
        new_film = cur.fetchone()
        return jsonify(new_film), 201
    except Exception as e:
        print("Error creating film:", e)
        return jsonify({"error": "Internal Server Error"}), 500
    finally:
        cur.close()
##############################
# New Endpoints for Update and Delete
##############################

# Update a film – admin only.


@app.route('/films/<int:film_id>', methods=['PUT'])
@jwt_required()
def update_film(film_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({"msg": "Access forbidden: Admins only"}), 403

    film_data = request.json
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE films
            SET title = %s, release_year = %s, runtime = %s, synopsis = %s, updated_at = NOW()
            WHERE film_id = %s
            RETURNING film_id, title, release_year, runtime, synopsis
        """, (
            film_data.get('title'),
            film_data.get('release_year'),
            film_data.get('runtime'),
            film_data.get('synopsis'),
            film_id
        ))
        if cur.rowcount == 0:
            abort(404, description="Film not found")
        updated_film = cur.fetchone()
        return jsonify(updated_film)
    except Exception as e:
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
