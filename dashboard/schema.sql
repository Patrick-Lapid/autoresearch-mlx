CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    iteration    INTEGER NOT NULL,
    started_at   REAL NOT NULL,
    ended_at     REAL,
    status       TEXT DEFAULT 'running',   -- running | completed | failed
    accepted     INTEGER,                  -- 1 | 0 | NULL
    val_bpb      REAL,
    parent_run_id TEXT,

    -- snapshot of all hyperparams from train.py
    depth               INTEGER,
    total_batch_size    INTEGER,
    device_batch_size   INTEGER,
    embedding_lr        REAL,
    unembedding_lr      REAL,
    matrix_lr           REAL,
    scalar_lr           REAL,
    weight_decay        REAL,
    warmup_ratio        REAL,
    warmdown_ratio      REAL,
    final_lr_frac       REAL,
    adam_betas          TEXT,   -- stored as JSON string e.g. "[0.8, 0.95]"
    window_pattern      TEXT,
    aspect_ratio        INTEGER,
    head_dim            INTEGER,
    time_budget         INTEGER,

    -- computed at run end
    num_params_m        REAL,
    total_tokens_m      REAL,
    num_steps           INTEGER,
    training_seconds    REAL,
    peak_vram_mb        REAL,
    mfu_percent         REAL,

    diff_patch          TEXT    -- unified diff of train.py vs parent
);

CREATE TABLE IF NOT EXISTS steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    step        INTEGER NOT NULL,
    wall_time   REAL NOT NULL,      -- seconds since run start
    loss        REAL,
    smooth_loss REAL,
    lrm         REAL,
    tok_per_sec INTEGER,
    pct_done    REAL,
    epoch       INTEGER,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS agent_notes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    TEXT NOT NULL,
    ts        REAL NOT NULL,
    intent    TEXT,
    hypothesis TEXT,
    raw       TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
