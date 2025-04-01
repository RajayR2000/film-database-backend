-- 1. Central Films Table
CREATE TABLE films (
  film_id SERIAL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  release_year INT,
  runtime VARCHAR(50),
  synopsis TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
 
-- 2. Locations Table (for mapping and geographic data)
CREATE TABLE locations (
  location_id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,   -- e.g., "Dakar, Senegal"
  address VARCHAR(255),
  city VARCHAR(100),
  state VARCHAR(100),
  country VARCHAR(100),
  latitude DECIMAL(9,6),
  longitude DECIMAL(9,6),
  comment TEXT
);
 
-- 3. Film Production Details (linking to a shooting location)
CREATE TABLE film_production_details (
  production_detail_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  production_timeframe VARCHAR(100), -- e.g., "1963"
  shooting_location_id INT REFERENCES locations(location_id) ON DELETE SET NULL,
  post_production_studio VARCHAR(255), -- stored as text if not visualized on a map
  production_comments TEXT
);
 
-- 4. Film Authors Table (e.g., screenwriter, filmmaker, executive producer)
CREATE TABLE film_authors (
  author_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  role VARCHAR(100),    -- e.g., "Screenwriter", "Filmmaker"
  name VARCHAR(255) NOT NULL,
  comment TEXT
);
 
-- 5. Film Production Team Table
CREATE TABLE film_production_team (
  team_member_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  department VARCHAR(100), -- e.g., "Image Technicians", "Sound Technicians", "Editing"
  name VARCHAR(255) NOT NULL,
  role VARCHAR(100),       -- Additional role details if needed
  comment TEXT
);
 
-- 6. Film Actors Table
CREATE TABLE film_actors (
  actor_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  actor_name VARCHAR(255) NOT NULL,
  character_name VARCHAR(255),  -- e.g., "Charretier"
  comment TEXT
);
 
-- 7. Film Equipment Table
CREATE TABLE film_equipment (
  equipment_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  equipment_name VARCHAR(255) NOT NULL, -- e.g., "Bell & Howell camera"
  description TEXT,                     -- e.g., description and technical details
  comment TEXT
);
 
-- 8. Film Documents Table
CREATE TABLE film_documents (
  document_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  document_type VARCHAR(100), -- e.g., "Script PDF"
  file_url TEXT,              -- URL or path to the document
  comment TEXT
);
 
-- 9. Institutional & Financial Information Table
CREATE TABLE film_institutional_info (
  info_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  production_company VARCHAR(255), -- e.g., "Film Domirev"
  funding_company VARCHAR(255),    -- e.g., "Actualités françaises"
  funding_comment TEXT,            -- details about funding provided
  source TEXT,                     -- reference or document source
  funding_location_id INT REFERENCES locations(location_id) ON DELETE SET NULL
);
 
-- 10. Film Screenings Table (linking to a location for mapping)
CREATE TABLE film_screenings (
  screening_id SERIAL PRIMARY KEY,
  film_id INT REFERENCES films(film_id) ON DELETE CASCADE,
  screening_date DATE,             -- Date of screening
  location_id INT REFERENCES locations(location_id) ON DELETE SET NULL,
  organizers VARCHAR(255),         -- e.g., names of organizers
  format VARCHAR(100),             -- e.g., "16 mm film copy", "35 mm film copy"
  audience VARCHAR(100),           -- Optional: audience details
  film_rights TEXT,                -- Film rights details if applicable
  comment TEXT,                    -- Additional notes
  source TEXT                      -- Reference source information
);

-- Below is a series of example SQL INSERT statements that populate the tables with data based on the example you provided for Borom Sarret. You can run these queries in order (after creating the tables) to insert sample data.
-- Note:
-- In these examples, we assume that the new film record gets an ID of 1 and that locations are inserted in order so that their auto‑generated IDs are as follows:
-- Dakar, Senegal (shooting location)
-- Paris, France (funding/post-production reference)
-- Karlovy Vary, Czech Republic
-- Montréal, Canada
-- Théâtre Sorano, Dakar, Senegal
-- Centre culturel français, Douala, Cameroon
-- Salle le Roxy, Dakar, Senegal

-- Insert the Film Record
INSERT INTO films (title, release_year, runtime, synopsis)
VALUES ('Borom Sarret', 1963, '20 minutes', 'A landmark film that signaled the birth of African cinema.');
-- Insert Locations
-- Shooting location: Dakar, Senegal
INSERT INTO locations (name, city, country)
VALUES ('Dakar, Senegal', 'Dakar', 'Senegal');
-- Funding / Post-production location: Paris, France
INSERT INTO locations (name, city, country)
VALUES ('Paris, France', 'Paris', 'France');
-- Screening location: Karlovy Vary, Czech Republic
INSERT INTO locations (name, city, country)
VALUES ('Karlovy Vary', 'Karlovy Vary', 'Czech Republic');
-- Screening location: Montréal, Canada
INSERT INTO locations (name, city, country)
VALUES ('Montréal', 'Montréal', 'Canada');
-- Screening location: Théâtre Sorano (Dakar, Senegal)
INSERT INTO locations (name, city, country)
VALUES ('Théâtre Sorano', 'Dakar', 'Senegal');
-- Screening location: Centre culturel français (Douala, Cameroon)
INSERT INTO locations (name, city, country)
VALUES ('Centre culturel français', 'Douala', 'Cameroon');
-- Screening location: Salle le Roxy (Dakar, Senegal)
INSERT INTO locations (name, city, country)
VALUES ('Salle le Roxy', 'Dakar', 'Senegal');


-- Insert Film Production Details
-- (Assuming the shooting location is Dakar, and the post‑production studio is in Paris)
INSERT INTO film_production_details (film_id, production_timeframe, shooting_location_id, post_production_studio, production_comments)
VALUES (1, '1963', 1, 'Paris', 'Shooting took place in Dakar; post-production performed in Paris.');
-- Insert Film Authors
INSERT INTO film_authors (film_id, role, name, comment)
VALUES 
  (1, 'Screenwriter', 'Ousmane Sembène', ''),
  (1, 'Filmmaker', 'Ousmane Sembène', ''),
  (1, 'Executive Producer', 'Paulin Vieyra', 'Not in the credits, nor in the contracts');
-- Insert Film Production Team
INSERT INTO film_production_team (film_id, department, name, role, comment)
VALUES 
  (1, 'Image Technicians', 'Christian Lacoste', '', ''),
  (1, 'Image Technicians', 'Ibrahima Barro', 'Assistant', ''),
  (1, 'Film Editor', 'André Gaudier', '', ''),
  (1, 'Music & Sound Designers', 'Amadou N’Diaye Sambe', '', ''),
  (1, 'Music & Sound Designers', 'Samba Diabaré Sambe', '', ''),
  (1, 'Music & Sound Designers', 'Mor Dior Seck', '', '');
-- Insert Film Actors
INSERT INTO film_actors (film_id, actor_name, character_name, comment)
VALUES (1, 'Ly Adboulaye', 'Borom Sarret (Charretier)', '');
-- Insert Film Equipment
INSERT INTO film_equipment (film_id, equipment_name, description, comment)
VALUES 
  (1, 'Bell & Howell camera', 'Combat caméra, robuste et à manivelle', 'Cartridge de 30m = 1 minute (version russe)'),
  (1, 'Arriflex camera', 'Caméra Arriflex capable of longer takes', 'Details from Vieyra, Les films Sénégalais, Étude critique');
-- Insert Film Documents
INSERT INTO film_documents (film_id, document_type, file_url, comment)
VALUES (1, 'Script PDF', 'http://example.com/borom_sarret_script.pdf', '');
-- Insert Institutional & Financial Information
-- (Funding company provided film stock and development funds in Paris.)
INSERT INTO film_institutional_info (film_id, production_company, funding_company, funding_comment, source, funding_location_id)
VALUES (1, 'Film Domirev', 'Actualités françaises', 'Provided film stock and paid for film stock development in Paris.', 'Zwobada, André, Note à M. Ousmane Sembène, Paris, July 1964, Lilly Library, BOX 24', 2);
-- Insert Film Screenings
-- Screening at Karlovy Vary, Czech Republic
INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
VALUES (1, '1964-08-01', 3, 'Dr. E. Hais', NULL, NULL, NULL, NULL, 'Dr. E. Hais, Z. Sebova, lettre (Praha, mai 1964, Lilly Library, BOX 1.)');
-- Screening at Montréal, Canada
INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
VALUES (1, '1964-08-01', 4, 'Rock Demers', NULL, NULL, NULL, NULL, 'Rock Demers, lettre (Montréal, mai 1964, Lilly Library, BOX 1.)');
-- Screening at Dakar (Festival mondial des Arts Négres)
INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
VALUES (1, '1966-04-01', 1, 'Paulin S. Vieyra', NULL, NULL, NULL, NULL, 'Vieyra, lettre (Dakar, février 1966, Lilly Library, BOX 1.)');
-- Screening at Théâtre Sorano, Dakar
INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
VALUES (1, '1967-02-01', 5, NULL, NULL, NULL, NULL, 'Soirée de Gala Cinématographique au profit du cinéma sénégalais. Plusieurs ministres présents.', 'Sembène, lettre (Dakar, janvier 1967, Lilly Library, BOX 1.)');
-- Screening at Centre culturel français, Douala, Cameroon
INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
VALUES (1, '1971-06-01', 6, 'Centre culturel français Douala', '16 mm film copy', NULL, 'Film copy owned by Cinémathèque du Département, achat de droits de diffusion non-commerciale', NULL, 'Archives diplomatiques (Nantes), 744PO/A/110');
-- Screening at Salle le Roxy, Dakar
INSERT INTO film_screenings (film_id, screening_date, location_id, organizers, format, audience, film_rights, comment, source)
VALUES (1, '1973-03-01', 7, 'SECMA – Sénégal', '35 mm film copy', NULL, 'Recettes : 53 100 Francs; Quote part du producteur : 15 358 Francs', NULL, 'SECMA – Sénégal, lettre, Semaine du cinéma sénégalais (Dakar, avril 1973, Lilly Library, BOX 1.)');

CREATE TABLE users (
  user_id SERIAL PRIMARY KEY,
  username VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(50) DEFAULT 'user',
  created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO users (username, password_hash, role)
VALUES (
  'admin', 
  '$2b$12$k8MSIR2SrTuTA1excJL0Fuw78uRrjeqolRcd4XU/OtGSxcB5nwxOW',
  'admin'
);
commit;