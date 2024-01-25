from argparse import ArgumentParser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from datetime import datetime
from tqdm import tqdm
import sys
import requests
import os
import time
import re

# download a page and save it locally
def save_page(content, folder, filename="index.html"):
    path = os.path.join(folder, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# used for "--mirror" flag
def mirror_download(url, folder, exclude=[]):
    parsed_url = urlparse(url)
    path_parts = os.path.split(parsed_url.path)
    
    # Vérifiez si le chemin de l'URL est dans la liste d'exclusion
    for path_to_exclude in exclude:
        if parsed_url.path.startswith(path_to_exclude):
            print(f"Excluded {url} because it matches the exclusion pattern: {path_to_exclude}")
            return None

    local_folder = os.path.join(folder, os.path.dirname(parsed_url.path).lstrip("/"))
    local_filename = os.path.join(local_folder, path_parts[-1] or "index.html")

    os.makedirs(local_folder, exist_ok=True)

    response = requests.get(url, stream=True)

    if response.status_code != 200:
        print(f"Failed to download {url}")
        return None

    with open(local_filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return local_filename


def download_page(url, reject=[], exclude=[], folder=None):
    domain = urlparse(url).netloc
    new_folder = domain if folder is None else folder
    if not os.path.exists(new_folder):
        os.mkdir(new_folder)

    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # download all images, scripts, and stylesheets
    tags = {'link': 'href', 'img': 'src', 'script': 'src'} 
    for tag, attr in tags.items():
        for link in soup.find_all(tag):
            src = link.get(attr)
            if src:
                src = urljoin(url, src)
                
                # Vérifiez si le chemin est dans la liste d'exclusion
                excluded = any(src.startswith(path_to_exclude) for path_to_exclude in exclude)

                
                if any(src.endswith(r) for r in reject) or excluded:
                    continue

                local_path = mirror_download(src, new_folder, exclude_paths)
                if local_path:
                    link[attr] = os.path.relpath(local_path, new_folder)

    # save the main html page with updated links
    save_page(str(soup), new_folder, "index.html")

# sanitize the filename to avoid any error
def sanitize_filename(filename):
    return "".join(c for c in filename if c not in ('<', '>', ':', '"', '/', '\\', '|', '?', '*'))

def download_file(url, rename, destination, rate_limit):
    file_name = url.split('/')[-1]
    if not file_name:
        print(f"No file name found in {url}")
        file_name = "default_filename.ext"

    # Rename the file
    if rename:
        file_name = rename
    
    # Move the file into a different folder
    file_path = os.path.expanduser(os.path.join(destination, file_name)) if destination else file_name


    if os.path.isdir(file_path):
        print(f"File path points to a directory, not a file: {file_path}")
        file_path = os.path.join(file_path, "default_filename.ext")

    print(f"Attempting to open file path: {file_path}")

    # rate limit
    if rate_limit:
        # find the rate limit value and unit (k, K, m, M)
        match = re.search(r'(\d+(?:\.\d+)?)([kKmM])', rate_limit)

        # if the rate limit is not specified, the value will be 0
        # if the rate limit is specified, the value will be the number of bytes per second (in float)
        rate_limit_value = float(match.group(1)) if rate_limit else 0

        # if match is not None, the unit will be k, K, m, or M
        unit = match.group(2) if match else ''

        if unit == 'k' or unit == 'K':
            rate_limit_value *= 1024
        elif unit == 'm' or unit == 'M':
            rate_limit_value *= 1024 * 1024
    else:
        rate_limit_value = 0

    byte_per_second = rate_limit_value

    response = requests.get(url, stream=True)

    if response.status_code == 200:
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        # tqdm is a progress bar library
        progress_bar = tqdm(total=total_size, unit='iB', unit_scale=True)
        # wb is for file that is opened for writing in binary mode
        byte_per_second = rate_limit_value
        with open(file_path, 'wb') as file:
            file_size = 0
            for chunk in response.iter_content(chunk_size=1024):
                start_time = time.time()
                file.write(chunk)
                file_size += len(chunk)
                progress_bar.update(len(chunk))

                expected_time = len(chunk) / byte_per_second if byte_per_second else 0

                time_to_sleep = expected_time - (time.time() - start_time)

                if time_to_sleep > 0:
                    time.sleep(time_to_sleep)

        progress_bar.close()
        print_info()
        # response.reason return the status code of the response ("OK" for 200, "Not Found" for 404, etc.)
        print("sending request, awaiting response...", response.status_code, "[", response.reason, "]")
        # as the file is downloaded in binary mode, we need to convert it to MB
        content_length = response.headers.get('content-length')
        if content_length:
            print("content size: ", content_length, "[~", round(int(content_length)/1000000, 2), "MB]")
        else:
            print("content size: Unknown")
        # absolute path of the file
        print("saving file to: ", os.path.abspath(file_path))
        print("Downloaded [" + url + "]")
        print("finished at: ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    else:
        print("Failed to download file")

def d_args():
    parser = ArgumentParser(description='Download files from the web')
    parser.add_argument('url', type=str, nargs='?', default=None, help='url to the file to be downloaded')
    parser.add_argument('-B', '--background', action='store_true', help='download the file in the background')
    parser.add_argument('-O','--rename', type=str, help='rename the file')
    parser.add_argument('-P', '--destination', type=str, help='move the downloaded file wherever you want')
    parser.add_argument('--rate-limit', help='rate the limit speed of download')
    parser.add_argument('-i', '--input-file', type=str, help='download multiple files from a file')
    parser.add_argument('--mirror', action='store_true', help='mirror a website')
    parser.add_argument('-R', '--reject', type=str, help='list of file suffixes to avoid')
    parser.add_argument('-X', '--exclude', type=str, help='list of paths to exclude')


    args = parser.parse_args()
    
    if not args.url and not args.input_file:
        parser.error("Please provide a url or a file")

    return args

def print_info():
    now = datetime.now()
    print("start at: ", now.strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == '__main__':
    args = d_args()
    if args.mirror:
        domain = urlparse(args.url).netloc
        folder_name = domain
        if not os.path.exists(folder_name):
            os.mkdir(folder_name)
        reject = args.reject.split(',') if args.reject else []
        exclude = args.exclude.split(',') if args.exclude else []
        exclude_paths = args.exclude.split(',') if args.exclude else []
        download_page(args.url, reject, exclude, folder=args.destination)


    if args.background:
        print("Output will be written to \"wget-log\".")
        sys.stdout = open("wget-log", "w")
    print_info()
    if args.input_file:
        with open(args.input_file, 'r') as file:
            urls = file.readlines()
            for url in urls:
                url = url.strip()
                download_file(url, args.rename, args.destination, args.rate_limit)
    elif args.url:
        download_file(args.url, args.rename, args.destination, args.rate_limit)
    else:
        print("Please specify the URL or the input file")    