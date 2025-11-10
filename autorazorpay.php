<?php
// =============================================
// RAZORPAY PHP API - RENDER OPTIMIZED v2.0
// =============================================

// Enable CORS for Render
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization");
header('Content-Type: application/json; charset=utf-8');

// Handle preflight requests
if ($_SERVER['REQUEST_METHOD'] == 'OPTIONS') {
    http_response_code(200);
    exit();
}

$errors = [];

// Get parameters with Render-specific defaults
$lista  = isset($_GET['lista']) ? trim($_GET['lista']) : null;
if (!$lista) {
    http_response_code(400);
    echo json_encode([
        'error' => true,
        'message' => 'Missing parameter: lista (format: CC|MM|YY|CVV)'
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

$amount = isset($_GET['amount']) ? trim($_GET['amount']) : '100';
$domain = isset($_GET['site']) ? trim($_GET['site']) : null;

if (!$domain) {
    http_response_code(400);
    echo json_encode([
        'error' => true,
        'message' => 'Missing parameter: site (Razorpay payment link)'
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

// Parse card data
$parts = explode('|', $lista);
if (count($parts) !== 4) {
    http_response_code(400);
    echo json_encode([
        'error' => true,
        'message' => 'Invalid lista format. Use CC|MM|YY|CVV'
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

$cc_raw  = $parts[0];
$mm_raw  = $parts[1];
$yy_raw  = $parts[2];
$cvv_raw = $parts[3];

$cc = preg_replace('/\D+/', '', $cc_raw);
$mm  = preg_replace('/\D+/', '', $mm_raw);
$yy  = preg_replace('/\D+/', '', $yy_raw);
$cvv = preg_replace('/\D+/', '', $cvv_raw);

if ($cc === '' || strlen($cc) < 9) {
    http_response_code(400);
    echo json_encode([
        'error' => true,
        'message' => 'Invalid card number. Must contain at least 9 digits.',
        'provided' => ['cc_raw' => $cc_raw]
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

$cc_full = $cc;
$cc_9    = substr($cc_full, 0, 9);

// Enhanced proxy system for Render
function getRandomProxyFromFile($file = 'proxy.txt') {
    if (!file_exists($file)) {
        // Return direct connection if no proxy file
        return null;
    }

    $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (empty($lines)) {
        return null;
    }

    $randomProxy = trim($lines[array_rand($lines)]);
    $randomProxy = preg_replace('/\s+/', '', $randomProxy);

    $parts = explode(':', $randomProxy);
    $proxy = [
        'host' => '',
        'port' => '',
        'user' => '',
        'pass' => ''
    ];

    if (count($parts) >= 4) {
        $proxy['host'] = $parts[0];
        $proxy['port'] = $parts[1];
        $proxy['user'] = $parts[2];
        $proxy['pass'] = implode(':', array_slice($parts, 3));
    } elseif (count($parts) === 3) {
        $proxy['host'] = $parts[0];
        $proxy['port'] = $parts[1];
        $proxy['user'] = $parts[2];
    } elseif (count($parts) === 2) {
        $proxy['host'] = $parts[0];
        $proxy['port'] = $parts[1];
    }

    return $proxy;
}

function applyProxy($ch, $proxy) {
    if ($proxy && isset($proxy['host'], $proxy['port'])) {
        curl_setopt($ch, CURLOPT_PROXY, $proxy['host'] . ':' . $proxy['port']);
        if (!empty($proxy['user']) && !empty($proxy['pass'])) {
            curl_setopt($ch, CURLOPT_PROXYUSERPWD, $proxy['user'] . ':' . $proxy['pass']);
        }
        // Render-specific timeout settings
        curl_setopt($ch, CURLOPT_TIMEOUT, 30);
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 15);
    }
}

// Enhanced fingerprint generation for Render
function generate_device_id() {
    $sha1_hex = sha1(random_bytes(20));
    $epoch_ms = (int)(microtime(true) * 1000);
    $rand8 = str_pad(random_int(0, 99999999), 8, '0', STR_PAD_LEFT);
    return "1.$sha1_hex.$epoch_ms.$rand8";
}

function generate_dynamic_user_fingerprint_v2() {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return bin2hex($data);
}

$device_id = generate_device_id();
$user_fingerprint_v2 = generate_dynamic_user_fingerprint_v2();
$contact = '+918' . str_pad((string) random_int(0, 999999999), 9, '0', STR_PAD_LEFT);
$random_email = 'user' . random_int(100000, 999999) . '@gmail.com';

$proxy = getRandomProxyFromFile();

// [REST OF YOUR ORIGINAL autorazorpay.php CODE CONTINUES HERE...]
// Include all your existing Razorpay processing logic
// Make sure to keep all the curl requests and data extraction

// At the end, ensure JSON response
$response_data = [
    'success' => true,
    'device_id' => $device_id,
    'session_data' => 'processed', // Add your actual response data
    'message' => 'Razorpay processing completed'
];

echo json_encode($response_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
?>
