# Restore deleted assets

## Usage

Set the missing assets path into the file `images.csv`.

Run the command:
```shell
docker run --rm -v $(pwd):/app php:8.1.28-cli php /app/index.php STORYBLOK_PERSONAL_TOKEN STORYBLOK_SPACE_ID
```