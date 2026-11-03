CREATE TABLE IF NOT EXISTS produits (
    sku   text PRIMARY KEY,
    nom   text NOT NULL,
    stock integer NOT NULL CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS commandes (
    id       serial PRIMARY KEY,
    ref      text UNIQUE NOT NULL,
    client   text NOT NULL,
    sku      text NOT NULL REFERENCES produits,
    quantite integer NOT NULL CHECK (quantite > 0),
    statut   text NOT NULL DEFAULT 'enregistrée',
    cree_le  timestamptz NOT NULL DEFAULT now()
);

-- Jeu de données initial, chargé une seule fois : 60 commandes réparties sur
-- 18 mois (certaines ont plus d'un an, pour l'archivage mensuel).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM produits) THEN
        INSERT INTO produits VALUES
            ('PAL-EUR',  'Palette Europe 800x1200',  500),
            ('CART-60',  'Carton 60x40x40',          2000),
            ('FILM-ETR', 'Film étirable 500 m',       300),
            ('SANG-PP',  'Sangle polypropylène',      800),
            ('ETIQ-A6',  'Étiquettes A6 (rouleau)',   150);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM commandes) THEN
        INSERT INTO commandes (ref, client, sku, quantite, statut, cree_le)
        SELECT 'CMD-H' || lpad(n::text, 4, '0'),
               (ARRAY['Brasserie du Nord', 'Menuiserie Martin', 'Fromagerie Alpine', 'Imprimerie Leroy'])[1 + n % 4],
               (ARRAY['PAL-EUR', 'CART-60', 'FILM-ETR', 'SANG-PP', 'ETIQ-A6'])[1 + n % 5],
               1 + n % 7,
               'expédiée',
               now() - n * interval '9 days'
        FROM generate_series(1, 60) AS n;
    END IF;
END $$;
