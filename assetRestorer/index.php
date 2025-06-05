<?php
const BASE_URL = 'https://mapi.storyblok.com/v1/spaces/%s/assets/';
const RESTORE_ASSETS_BULK_SIZE = 20;

function searchAssetByUrl($url, $token, $spaceId) {
	$urlParts = explode('/', $url);
	$search = sprintf(
		'%s/%s', 
		$urlParts[count($urlParts)-2], 
		end($urlParts)
	);

	$ch = curl_init();
	
	$headers = [
		'Authorization: ' . $token,
		'Content-Type:application/json'
	];
	curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

	curl_setopt($ch, CURLOPT_URL, sprintf(BASE_URL . '?search=%s&per_page=500&in_folder=-1', $spaceId, urlencode($search)));
	curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

	$output = curl_exec($ch);
	curl_close($ch);

	$output = json_decode($output, true);

	if (!empty($output['assets'])) {
		return $output['assets'][0]['id'];
	}

	return null;
}

function restoreAssets($ids, $token, $spaceId) {
	$ch = curl_init();
	$headers = [
		'Authorization: ' . $token,
		'Content-Type:application/json'
	];

	$payload = json_encode(["ids"=> $ids]);
	curl_setopt( $ch, CURLOPT_POSTFIELDS, $payload );

	curl_setopt($ch, CURLOPT_URL, sprintf(BASE_URL . 'bulk_restore', $spaceId));
	curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
	curl_setopt($ch, CURLOPT_POST, true);

	curl_exec($ch);
	curl_close($ch);

	echo 'Restored images: ' . print_r($ids, 1);
}

$token = $argv[0];
$spaceId = $argv[1];

$imagesFile = @fopen(__DIR__ . "/images.csv", "r");
if (!$imagesFile) {
	echo "Not images.csv file found\n";

	return;
}

$retrievedImages = [];

while($url = fgets($imagesFile, 4096)) {
	if ($imageId = searchAssetByUrl($url, $token, $spaceId)) {
		echo 'Found ' . $url;
		$retrievedImages[] = $imageId;
		
		if (count($retrievedImages) >= RESTORE_ASSETS_BULK_SIZE) {
			restoreAssets($retrievedImages);
			$retrievedImages = [];
		}
	} else {
		echo 'Not found ' . $url;
	}
}

fclose($imagesFile);

if (!empty($retrievedImages)) {
	restoreAssets($retrievedImages);
}

echo "\n";