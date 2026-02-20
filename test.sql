SELECT
    conrelid::regclass AS table_from,
    a.attname AS column_from,
    confrelid::regclass AS table_to,
    af.attname AS column_to
FROM
    pg_constraint
JOIN pg_attribute a ON a.attnum = ANY(conkey) AND a.attrelid = conrelid
JOIN pg_attribute af ON af.attnum = ANY(confkey) AND af.attrelid = confrelid
WHERE contype = 'f';