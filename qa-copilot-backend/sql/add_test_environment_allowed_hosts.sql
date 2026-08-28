BEGIN;

ALTER TABLE test_environments
    ADD COLUMN IF NOT EXISTS allowed_hosts JSONB NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_test_environments_allowed_hosts_array'
          AND conrelid = 'test_environments'::regclass
    ) THEN
        ALTER TABLE test_environments
            ADD CONSTRAINT chk_test_environments_allowed_hosts_array
            CHECK (jsonb_typeof(allowed_hosts) = 'array');
    END IF;
END
$$;

COMMIT;
