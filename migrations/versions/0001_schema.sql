CREATE TABLE groups (
	id SERIAL NOT NULL,
	name VARCHAR(100) NOT NULL,
	size INTEGER NOT NULL,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CHECK (size > 0),
	UNIQUE (name)
)

;


CREATE TABLE login_attempts (
	id SERIAL NOT NULL,
	key VARCHAR(64) NOT NULL,
	created TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_login_attempts_created ON login_attempts (created);
CREATE INDEX ix_login_attempts_key ON login_attempts (key);

CREATE TABLE periods (
	id SERIAL NOT NULL,
	name VARCHAR(150) NOT NULL,
	start DATE NOT NULL,
	"end" DATE NOT NULL,
	PRIMARY KEY (id),
	CHECK ("end" >= start)
)

;


CREATE TABLE rooms (
	id SERIAL NOT NULL,
	name VARCHAR(100) NOT NULL,
	capacity INTEGER NOT NULL,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CHECK (capacity > 0),
	UNIQUE (name)
)

;


CREATE TABLE subjects (
	id SERIAL NOT NULL,
	name VARCHAR(150) NOT NULL,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
)

;


CREATE TABLE teachers (
	id SERIAL NOT NULL,
	name VARCHAR(150) NOT NULL,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name)
)

;


CREATE TABLE users (
	id SERIAL NOT NULL,
	username VARCHAR(80) NOT NULL,
	name VARCHAR(150) NOT NULL,
	password_hash VARCHAR(256) NOT NULL,
	role VARCHAR(20) NOT NULL,
	active BOOLEAN NOT NULL,
	group_id INTEGER,
	teacher_id INTEGER,
	PRIMARY KEY (id),
	CHECK (role IN ('admin','dispatcher','teacher','student')),
	UNIQUE (username),
	FOREIGN KEY(group_id) REFERENCES groups (id),
	FOREIGN KEY(teacher_id) REFERENCES teachers (id)
)

;


CREATE TABLE schedules (
	id SERIAL NOT NULL,
	name VARCHAR(150) NOT NULL,
	period_id INTEGER NOT NULL,
	status VARCHAR(20) NOT NULL,
	author_id INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (status IN ('draft','published')),
	FOREIGN KEY(period_id) REFERENCES periods (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
)

;


CREATE TABLE series (
	id SERIAL NOT NULL,
	request_key VARCHAR(100) NOT NULL,
	author_id INTEGER NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (author_id, request_key),
	FOREIGN KEY(author_id) REFERENCES users (id)
)

;


CREATE TABLE sessions (
	token_hash VARCHAR(64) NOT NULL,
	user_id INTEGER NOT NULL,
	csrf VARCHAR(80) NOT NULL,
	expires TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;


CREATE TABLE lessons (
	id SERIAL NOT NULL,
	schedule_id INTEGER NOT NULL,
	group_id INTEGER NOT NULL,
	teacher_id INTEGER NOT NULL,
	room_id INTEGER NOT NULL,
	subject_id INTEGER NOT NULL,
	series_id INTEGER,
	starts TIMESTAMP WITH TIME ZONE NOT NULL,
	ends TIMESTAMP WITH TIME ZONE NOT NULL,
	status VARCHAR(20) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	version INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (ends > starts),
	CHECK (status IN ('planned','moved','cancelled')),
	CONSTRAINT no_overlap_group_id EXCLUDE USING gist (group_id WITH =, tstzrange(starts, ends, '[)') WITH &&) WHERE (status <> 'cancelled'),
	CONSTRAINT no_overlap_teacher_id EXCLUDE USING gist (teacher_id WITH =, tstzrange(starts, ends, '[)') WITH &&) WHERE (status <> 'cancelled'),
	CONSTRAINT no_overlap_room_id EXCLUDE USING gist (room_id WITH =, tstzrange(starts, ends, '[)') WITH &&) WHERE (status <> 'cancelled'),
	FOREIGN KEY(schedule_id) REFERENCES schedules (id),
	FOREIGN KEY(group_id) REFERENCES groups (id),
	FOREIGN KEY(teacher_id) REFERENCES teachers (id),
	FOREIGN KEY(room_id) REFERENCES rooms (id),
	FOREIGN KEY(subject_id) REFERENCES subjects (id),
	FOREIGN KEY(series_id) REFERENCES series (id)
)

;
CREATE INDEX ix_lessons_group_id ON lessons (group_id);
CREATE INDEX ix_lessons_teacher_id ON lessons (teacher_id);
CREATE INDEX ix_lessons_starts ON lessons (starts);
CREATE INDEX ix_lessons_room_id ON lessons (room_id);
CREATE INDEX ix_lessons_schedule_id ON lessons (schedule_id);

CREATE TABLE audit (
	id SERIAL NOT NULL,
	lesson_id INTEGER,
	schedule_id INTEGER NOT NULL,
	actor_id INTEGER NOT NULL,
	action VARCHAR(40) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	before JSON NOT NULL,
	after JSON NOT NULL,
	created TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(lesson_id) REFERENCES lessons (id),
	FOREIGN KEY(schedule_id) REFERENCES schedules (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;
CREATE INDEX ix_audit_lesson_id ON audit (lesson_id);
