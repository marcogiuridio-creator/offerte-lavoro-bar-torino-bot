SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT SIGNED PRIMARY KEY,
    username VARCHAR(255) NULL,
    first_name VARCHAR(255) NULL,
    last_name VARCHAR(255) NULL,
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_post DATETIME NULL,
    posts_today INT NOT NULL DEFAULT 0,
    last_date DATE NULL,
    is_banned TINYINT(1) NOT NULL DEFAULT 0,
    is_verified TINYINT(1) NOT NULL DEFAULT 0,
    role VARCHAR(32) NULL,
    offerte_count INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS posts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT SIGNED NULL,
    message_id BIGINT SIGNED NULL,
    category VARCHAR(32) NULL,
    text TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_featured TINYINT(1) NOT NULL DEFAULT 0,
    featured_until DATETIME NULL,
    converted_job_id BIGINT UNSIGNED NULL,
    INDEX idx_posts_created (created_at),
    INDEX idx_posts_user_message (user_id, message_id),
    CONSTRAINT fk_posts_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bot_settings (
    `key` VARCHAR(191) PRIMARY KEY,
    value TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS banned_words (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    word VARCHAR(191) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS stats_daily (
    `date` DATE PRIMARY KEY,
    new_members INT NOT NULL DEFAULT 0,
    posts_total INT NOT NULL DEFAULT 0,
    offerte INT NOT NULL DEFAULT 0,
    richieste INT NOT NULL DEFAULT 0,
    spam_blocked INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS candidate_profiles (
    user_id BIGINT SIGNED PRIMARY KEY,
    username VARCHAR(255) NULL,
    first_name VARCHAR(255) NULL,
    roles JSON NULL,
    skills JSON NULL,
    experience TEXT NULL,
    availability JSON NULL,
    zones JSON NULL,
    phone VARCHAR(64) NULL,
    bio TEXT NULL,
    is_premium TINYINT(1) NOT NULL DEFAULT 0,
    premium_until DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_candidate_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS job_offers (
    job_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT SIGNED NOT NULL,
    username VARCHAR(255) NULL,
    business_name VARCHAR(255) NOT NULL,
    role VARCHAR(255) NOT NULL,
    zone VARCHAR(255) NOT NULL,
    shift VARCHAR(255) NULL,
    salary VARCHAR(255) NULL,
    description TEXT NULL,
    contact VARCHAR(255) NULL,
    package VARCHAR(32) NOT NULL DEFAULT 'base',
    is_verified TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message_id BIGINT SIGNED NULL,
    promotion_ended_at DATETIME NULL,
    INDEX idx_jobs_user (user_id),
    INDEX idx_jobs_created (created_at),
    CONSTRAINT fk_jobs_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS applications (
    app_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    job_id BIGINT UNSIGNED NOT NULL,
    candidate_id BIGINT SIGNED NOT NULL,
    candidate_user VARCHAR(255) NULL,
    match_score INT NULL,
    screening_q1 TEXT NULL,
    screening_q2 TEXT NULL,
    screening_notes TEXT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_application_job_candidate (job_id, candidate_id),
    CONSTRAINT fk_application_job FOREIGN KEY (job_id) REFERENCES job_offers(job_id),
    CONSTRAINT fk_application_candidate FOREIGN KEY (candidate_id) REFERENCES candidate_profiles(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS security_events (
    event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    user_id BIGINT SIGNED NULL,
    username VARCHAR(255) NULL,
    chat_id BIGINT SIGNED NULL,
    message_id BIGINT SIGNED NULL,
    visible_text TEXT NULL,
    target TEXT NULL,
    details TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_security_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payment_events (
    transaction_id VARCHAR(191) PRIMARY KEY,
    user_id BIGINT SIGNED NOT NULL,
    payload VARCHAR(255) NOT NULL,
    currency VARCHAR(16) NOT NULL,
    amount INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS telegram_updates (
    update_id BIGINT SIGNED PRIMARY KEY,
    received_at DATETIME NOT NULL,
    processed_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS application_sessions (
    candidate_id BIGINT SIGNED NOT NULL,
    job_id BIGINT UNSIGNED NOT NULL,
    screening_q1 VARCHAR(255) NULL,
    screening_q2 VARCHAR(255) NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (candidate_id, job_id),
    CONSTRAINT fk_session_candidate FOREIGN KEY (candidate_id) REFERENCES users(user_id),
    CONSTRAINT fk_session_job FOREIGN KEY (job_id) REFERENCES job_offers(job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
