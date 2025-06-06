#!/usr/bin/env python3

import argparse
import json
import pathlib
import re
import shutil
import os
from os import getenv, makedirs, path

import requests

_storyblok_space_id = None
_storyblok_personal_access_token = None


def init_storyblok_client(space_id, token):
    # TODO: make this cleaner without changing too much code
    global _storyblok_space_id
    global _storyblok_personal_access_token

    _storyblok_space_id = space_id
    _storyblok_personal_access_token = token


def request(method, path, params=None, **kwargs):
    BASE_URL = 'https://mapi.storyblok.com'

    return requests.request(
        method,
        f'{BASE_URL}/v1/spaces/{_storyblok_space_id}{path}',
        headers={
            'Authorization': _storyblok_personal_access_token,
        },
        params=params,
        **kwargs,
    )


def ensure_cache_dir_exists(cache_directory):
    if not path.exists(cache_directory):
        makedirs(cache_directory)


def load_json(file_path):
    print(f'Loading {file_path}')
    with open(file_path, 'r') as file:
        return json.load(file)


def save_json(file_path, data):
    try:
        with open(file_path, 'w') as file:
            return json.dump(data, file, indent=2, ensure_ascii=True)
    except KeyboardInterrupt as e:
        print("KeyboardInterrupt: Saving file again!")
        save_json(file_path, data)
        raise e


def download_asset(asset_url, target_file_path, continue_download_on_failure):
    print(f'Attempting to download asset from {asset_url} to {target_file_path}')

    response = requests.get(asset_url, stream=True)

    if response.status_code == 200:
        print(f'Successfully initiated download for {asset_url}. Writing to {target_file_path}')
        os.makedirs(path.dirname(target_file_path), exist_ok=True)
        with open(target_file_path, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        print(f'Download completed successfully for {asset_url}')
    else:
        msg = f'Failed to download asset {asset_url}. HTTP status code: {response.status_code}'

        if continue_download_on_failure:
            print(
                msg +
                '. Continuing with the next asset due to '
                '--continue-download-on-failure flag.'
            )
        else:
            print(msg + '. Stopping the download process.')
            raise RuntimeError(
                msg +
                '. Use --continue-download-on-failure to ignore this error and continue.'
            )


def get_all_paginated(
    path,
    item_name,
    params={},
    max_pages=None,
    start_page=1,
    max_items=None,
):
    page = start_page
    all_items = []
    pages_processed = 0

    while (
        page is not None
        and (max_pages is None or pages_processed < max_pages)
        and (max_items is None or len(all_items) < max_items)
    ):
        print(f'Getting {path}, page={page}')

        params = {
            'per_page': 100,
            **params,
            'page': page,
        }

        response = request(
            'GET',
            path,
            params=params
        )

        response.raise_for_status()
        response_data = response.json()

        if item_name not in response_data and isinstance(response_data, dict):
            raise KeyError(
                'item_name {!r} not in response. Possible keys {}'.format(
                    item_name,
                    ", ".join(response_data.keys())
                )
            )

        new_items = response_data[item_name]

        if max_items is not None:
            remaining = max_items - len(all_items)
            new_items = new_items[:remaining]

        if len(new_items) < int(params['per_page']) or (
            max_items is not None and len(all_items) + len(new_items) >= max_items
        ):
            page = None
        else:
            page += 1

        all_items.extend(new_items)
        pages_processed += 1

    return all_items


def is_asset_in_use(asset):
    file_path = asset['filename'].replace('https://s3.amazonaws.com/a.storyblok.com', '')

    response = request(
        'GET',
        '/stories',
        params={
            'reference_search': file_path,
            'per_page': 1,
            'page': 1,
        }
    )

    response.raise_for_status()

    stories = response.json()['stories']

    return len(stories) != 0


ASSET_URL_PATTERN = re.compile(r"https://[^\s\"'>]+\.storyblok\.com/[^\s\"'>]+")


def _extract_storyblok_urls(data):
    urls = set()

    if isinstance(data, dict):
        for value in data.values():
            urls.update(_extract_storyblok_urls(value))
    elif isinstance(data, list):
        for item in data:
            urls.update(_extract_storyblok_urls(item))
    elif isinstance(data, str):
        urls.update(re.findall(ASSET_URL_PATTERN, data))

    return urls


def get_html_referenced_assets_from_stories(stories):
    referenced_urls = set()

    for story in stories:
        content = story.get('content')
        if content:
            referenced_urls.update(_extract_storyblok_urls(content))

    return referenced_urls


def _main():
    parser = argparse.ArgumentParser(
        description='storyblok-assets-cleanup an utility to delete unused assets.'
    )

    parser.add_argument(
        '--delete',
        action=argparse.BooleanOptionalAction,
        type=bool,
        default=False,
        help='If we should delete assets, default to false.',
    )
    parser.add_argument(
        '--backup',
        action=argparse.BooleanOptionalAction,
        type=bool,
        default=True,
        help='If we should backup assets (to ./assets_backup/<SPACE_ID>), defaults to true.',
    )
    parser.add_argument(
        '--cache',
        action=argparse.BooleanOptionalAction,
        type=bool,
        default=True,
        help=(
            'If we should use cache the assets index. Defaults to True (recommended).'
        ),
    )
    parser.add_argument(
        '--continue-download-on-failure',
        action=argparse.BooleanOptionalAction,
        type=bool,
        default=True,
        help='If we should continue if the download of an asset fails. Defaults to true.',
    )

    parser.add_argument(
        '--space-id',
        type=str,
        default=getenv('STORYBLOK_SPACE_ID'),
        required=getenv('STORYBLOK_SPACE_ID') is None,
        help=(
            'Storyblok space ID, alternatively use the env var STORYBLOK_SPACE_ID.'
        ),
    )
    parser.add_argument(
        '--token',
        type=str,
        default=getenv('STORYBLOK_PERSONAL_ACCESS_TOKEN'),
        required=getenv('STORYBLOK_PERSONAL_ACCESS_TOKEN') is None,
        help=(
            'Storyblok personal access token, '
            'alternatively use the env var STORYBLOK_PERSONAL_ACCESS_TOKEN.'
        ),
    )
    parser.add_argument(
        '--blacklisted-folder-paths',
        type=str,
        default=getenv('BLACKLISTED_ASSET_FOLDER_PATHS', ''),
        help=(
            'Comma separated list of filepaths that should be ignored. '
            'Alternatively use the env var BLACKLISTED_ASSET_FOLDER_PATHS. '
            'Default to none/empty list.'
        ),
    )
    parser.add_argument(
        '--blacklisted-words',
        type=str,
        default=getenv('BLACKLISTED_ASSET_FILENAME_WORDS', ''),
        help=(
            'Comma separated list of words that should be used to ignore assets when they are '
            'contained in its filename. '
            'Alternatively use the env var BLACKLISTED_ASSET_FILENAME_WORDS. '
            'Default to none/empty list.'
        ),
    )
    parser.add_argument(
        '--cache-directory',
        type=str,
        default='cache',
        help='Cache directory, defaults to ./cache.',
    )
    parser.add_argument(
        '--backup-directory',
        type=str,
        default='assets_backup',
        help='Backup directory, defaults to ./assets_backup.',
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=None,
        help='Maximum number of pages to process. If not set, all pages will be processed.',
    )
    parser.add_argument(
        '--max-assets',
        type=int,
        default=None,
        help='Maximum number of assets to process. If not set, all assets will be processed.',
    )
    parser.add_argument(
        '--start-page',
        type=int,
        default=1,
        help='Start page to proceed. If not set, first page will be processed.',
    )
    parser.add_argument(
        '--max-story-pages',
        type=int,
        default=None,
        help=(
            'Maximum number of story pages to process when searching HTML. '
            'If not set, all pages will be processed.'
        ),
    )

    args = parser.parse_args()

    init_storyblok_client(args.space_id, args.token)
    should_delete_images = args.delete
    use_cache = args.cache
    backup_assets = args.backup
    space_id = args.space_id
    continue_download_on_failure = args.continue_download_on_failure
    blacklisted_asset_folder_paths = args.blacklisted_folder_paths.split(',')
    blacklisted_asset_filename_words = args.blacklisted_words.split(',')
    cache_directory = args.cache_directory
    backup_directory = args.backup_directory
    max_pages = args.max_pages
    max_assets = args.max_assets
    start_page = args.start_page
    max_story_pages = args.max_story_pages
    assets_cache_path = path.join(cache_directory, f'{space_id}_assets.json')
    asset_folder_cache_path = path.join(cache_directory, f'{space_id}_asset_folders.json')

    ensure_cache_dir_exists(cache_directory)

    all_assets = None
    all_folders = None

    if path.exists(assets_cache_path) and use_cache:
        all_assets = load_json(assets_cache_path)
        if max_assets is not None:
            all_assets = all_assets[:max_assets]
    else:
        all_assets = get_all_paginated(
            '/assets',
            item_name='assets',
            max_pages=max_pages,
            start_page=start_page,
            max_items=max_assets,
        )
        save_json(assets_cache_path, all_assets)

    if path.exists(asset_folder_cache_path) and use_cache:
        all_folders = load_json(asset_folder_cache_path)
    else:
        all_folders = get_all_paginated('/asset_folders', item_name='asset_folders')
        save_json(asset_folder_cache_path, all_folders)

    folder_ids_to_folder = {
        folder['id']: folder
        for folder in all_folders
    }

    stories_cache_path = path.join(cache_directory, f'{space_id}_stories.json')

    if path.exists(stories_cache_path) and use_cache:
        all_stories = load_json(stories_cache_path)
    else:
        all_stories = get_all_paginated(
            '/stories',
            item_name='stories',
            max_pages=max_story_pages,
            start_page=1,
        )
        save_json(stories_cache_path, all_stories)

    html_referenced_assets = {
        url.split('?', 1)[0]
        for url in get_html_referenced_assets_from_stories(all_stories)
    }

    def get_folder_path_name(folder_id):
        if folder_id not in folder_ids_to_folder:
            print(f'Warning: Folder with ID {folder_id} does not exist.')
            return None

        folder = folder_ids_to_folder[folder_id]
        name = folder['name']

        if folder['parent_id'] in [None, '', 0, '0']:
            return f'/{name}'

        if folder['parent_id'] not in folder_ids_to_folder:
            print(f'Warning: Parent folder of {folder["id"]} does not exist. Skipping folder.')
            return None

        parent_path = get_folder_path_name(folder['parent_id'])
        if parent_path is None:
            return None

        return f'{parent_path}/{name}'

    def should_be_deleted(asset_path_name, filename):
        if blacklisted_asset_folder_paths:
            for blacklisted_path in blacklisted_asset_folder_paths:
                if blacklisted_path and blacklisted_path in asset_path_name:
                    print(
                        f'Skipping asset ID {id} as its path {asset_path_name} '
                        f'is blacklisted due to the path: "{blacklisted_path}"'
                    )
                    return False

        if blacklisted_asset_filename_words:
            for blacklisted_word in blacklisted_asset_filename_words:
                if blacklisted_word and blacklisted_word.lower() in filename.lower():
                    print(
                        f'Skipping asset ID {id} as its filename "{filename}" '
                        f'contains blacklisted word: "{blacklisted_word}"'
                    )
                    return False

        return True

    print('Checking for assets in use. This might take a while.')

    count = 0
    for asset in all_assets:
        if 'is_in_use' in asset:
            continue

        clean_url = asset['filename'].split('?', 1)[0]
        asset['html_in_use'] = clean_url in html_referenced_assets
        asset['is_in_use'] = asset['html_in_use'] or is_asset_in_use(asset)
        asset['to_be_deleted'] = False

        count += 1

        if count % 100 == 0:
            print(f'{count}/{len(all_assets)}')
            save_json(assets_cache_path, all_assets)

    assets_not_in_use = [
        asset
        for asset in all_assets
        if not asset['is_in_use'] and not asset.get('is_deleted', False)
    ]

    folder_id_to_path_name = {
        folder['id']: get_folder_path_name(folder['id'])
        for folder in all_folders
    }

    folder_id_to_path_name[None] = '/'

    folder_path_names_to_item_counts = {}

    total_size_to_delete = 0
    total_count_to_delete = 0

    for asset in assets_not_in_use:
        id = asset["id"]

        asset_path_name = folder_id_to_path_name[asset['asset_folder_id']]
        asset_size = asset.get('content_length', 0) or 0

        to_be_deleted = should_be_deleted(asset_path_name, asset["filename"])
        asset['to_be_deleted'] = to_be_deleted

        if asset['to_be_deleted']:
            print(f"Asset ID {id} marked for deletion.")
            total_size_to_delete += asset_size
            total_count_to_delete += 1
        else:
            print(
                f"Asset ID {id} will not be deleted. Either in use, "
                "blacklisted, or an error occurred."
            )

        not_in_use_count, to_be_deleted_count = folder_path_names_to_item_counts.get(
            asset_path_name,
            (0, 0),
        )
        folder_path_names_to_item_counts[asset_path_name] = (
            not_in_use_count + 1,
            to_be_deleted_count + (1 if asset['to_be_deleted'] else 0)
        )

    print('\nSummary of files to be deleted')
    TITLES = [
        'Not in use',
        'To be deleted',
        'Path',
    ]

    def print_padded(outputs):
        print(
            " | ".join([
                (
                    str(output).rjust(len(TITLES[index]), " ")
                    if isinstance(output, int) else
                    str(output).ljust(len(TITLES[index]), " ")
                )
                for index, output in enumerate(outputs)
            ])
        )

    print_padded(TITLES)

    for path_name in sorted(folder_path_names_to_item_counts.keys()):
        not_in_use_count, to_be_deleted_count = folder_path_names_to_item_counts[path_name]

        print_padded([
            not_in_use_count,
            to_be_deleted_count,
            path_name,
        ])

    print()

    print(
        f'\nTotal size to be freed: {total_size_to_delete} bytes '
        f'({total_size_to_delete / (1024*1024):.2f} MB)'
    )
    print(f'Total count to be deleted: {total_count_to_delete} assets\n')

    if should_delete_images:
        user_confirmation = input('Do you really want to delete the assets? (y/n): ')
        if user_confirmation.lower() == 'y':
            for asset in assets_not_in_use:
                if asset.get('to_be_deleted'):
                    print(f'Deleting asset {asset["id"]}')
        else:
            print("Deletion canceled by the user.")
            should_delete_images = False
    elif backup_assets:
        input('Images will not be deleted but will perform backup. Press any key to continue: ')
    else:
        input('Dry run mode: nothing will be done. Press any key to continue: ')

    for asset in assets_not_in_use:
        id = asset["id"]
        filename = pathlib.Path(asset["filename"]).name
        asset_path_name = folder_id_to_path_name[asset['asset_folder_id']]

        if backup_assets and asset.get('to_be_deleted'):
            print(f'Starting backup process for asset ID {id}, filename: {filename}')
            if 'backed_up_to' not in asset or asset['backed_up_to'] is None:
                file_path = path.join(
                    backup_directory,
                    space_id,
                    asset_path_name.lstrip('/'),
                    filename,
                )
                try:
                    download_asset(asset["filename"], file_path, continue_download_on_failure)
                    asset['backed_up_to'] = file_path
                    print(f'Backup successful for asset ID {id}, saved to {file_path}')
                except Exception as e:
                    print(f'Error during backup of asset ID {id}, filename: {filename}. Error: {e}')
            else:
                print(
                    f'Asset ID {id}, filename: {filename} has already been '
                    f'backed up to {asset["backed_up_to"]}'
                )

        if should_delete_images and asset.get('to_be_deleted'):
            print(f'Attempting to delete asset ID {id}, filename: {filename}')
            response = request('DELETE', f'/assets/{id}')
            if response.status_code == 200:
                asset['is_deleted'] = True
                print(f'Deletion successful for asset ID {id}')
            else:
                print(f'Failed to delete asset ID {id}. HTTP status code: {response.status_code}')
        else:
            print(
                f'Would attempt to delete asset ID {id}, filename: {filename} '
                'if --delete was specified'
            )

        if backup_assets or should_delete_images:
            save_json(assets_cache_path, all_assets)


def main():
    try:
        _main()
    except KeyboardInterrupt:
        print('\nInterrupted, exiting...')


if __name__ == '__main__':
    main()
