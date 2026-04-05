<?php
/**
 * click.php — Tracking de clics en enlaces de afiliado
 *
 * Parámetros GET:
 *   asin     — ASIN del producto Amazon (requerido)
 *   post_id  — ID del post de WordPress (opcional)
 *   position — posición en el post: top / middle / bottom (opcional)
 *
 * Registra el clic en ir_affiliate_clicks y redirige a Amazon.
 * Tiempo objetivo: < 50ms (solo INSERT + redirect).
 */

define('AFFILIATE_TAG', 'inforeparto-21');

define('DB_HOST', 'localhost');
define('DB_USER', 'wp_user');
define('DB_PASS', '2R9EUs4FDYlc');
define('DB_NAME', 'wordpress_db');

// ── Validar parámetros ────────────────────────────────────────────────────────

$asin = isset($_GET['asin']) ? preg_replace('/[^A-Z0-9]/i', '', $_GET['asin']) : '';
$post_id = isset($_GET['post_id']) ? (int)$_GET['post_id'] : null;
$position = isset($_GET['position']) ? preg_replace('/[^a-z]/', '', strtolower($_GET['position'])) : 'unknown';

// Validar ASIN: 10 caracteres alfanuméricos
if (!preg_match('/^[A-Z0-9]{10}$/i', $asin)) {
    http_response_code(400);
    exit('Invalid ASIN');
}

$allowed_positions = ['top', 'middle', 'bottom', 'unknown'];
if (!in_array($position, $allowed_positions)) {
    $position = 'unknown';
}

// ── Registrar clic ────────────────────────────────────────────────────────────

$user_agent = substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 500);
$referer    = substr($_SERVER['HTTP_REFERER'] ?? '', 0, 500);

try {
    $pdo = new PDO(
        "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=utf8mb4",
        DB_USER,
        DB_PASS,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_TIMEOUT => 2]
    );

    $stmt = $pdo->prepare(
        "INSERT INTO ir_affiliate_clicks (asin, post_id, position, user_agent, referer)
         VALUES (:asin, :post_id, :position, :ua, :ref)"
    );
    $stmt->execute([
        ':asin'     => strtoupper($asin),
        ':post_id'  => $post_id,
        ':position' => $position,
        ':ua'       => $user_agent,
        ':ref'      => $referer,
    ]);
} catch (Exception $e) {
    // No bloqueamos la redirección si falla el INSERT
    error_log("ir_affiliate_clicks insert error: " . $e->getMessage());
}

// ── Redirigir a Amazon ────────────────────────────────────────────────────────

$amazon_url = "https://www.amazon.es/dp/" . strtoupper($asin) . "/?tag=" . AFFILIATE_TAG;

header("Location: " . $amazon_url, true, 302);
header("Cache-Control: no-store, no-cache");
exit;
