ALTER TABLE job_offers
    ADD COLUMN IF NOT EXISTS promotion_expires_at DATETIME NULL AFTER message_id,
    ADD COLUMN IF NOT EXISTS last_bumped_at DATETIME NULL AFTER promotion_expires_at;
