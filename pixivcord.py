#!/usr/bin/env python3
import json
import pixivpy3
from retry import retry
import requests
import logging
import time
import os
import pprint
import images
import traceback

from config import REFRESH_TOKEN


class SanityLevel:
    UNCHECKED = 0
    GRAY = 1
    WHITE = 2
    SEMI_BLACK = 4
    BLACK = 6


class Rating:
    ALL = 0
    R18 = 1
    R18G = 2


SLEEP_TIME = 60 * 5
logger = None
global_settings = None

BLACKLIST_REASONS = {
    "nsfw-in-sfw": "Post is NSFW in a SFW-only feed.",
    "sfw-in-nsfw": "Post is SFW in a NSFW-only feed.",
    "bad-tag": "Post containted a blacklisted tag.",
    "bad-user": "Post was made by a blacklisted user."
}

api = pixivpy3.AppPixivAPI()

# These are for ratelimits while posting.
ratelimit_left = 0
ratelimit_wait = 0


def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    handler = logging.FileHandler('output.log', 'w', )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


@retry(requests.exceptions.HTTPError, tries=5, delay=1, backoff=2, jitter=(0, 2), logger=logger)
def make_post(feed, post):
    global ratelimit_left, ratelimit_wait
    try:
        webhook_post = requests.post(feed['webhook'], json=post)
        logger.info(f"Response code {webhook_post.status_code} for post in {feed['id']}")
        webhook_post.raise_for_status()

        # Get ratelimit info: number of posts remaining before
        # we hit the limit, and time left before remaining posts
        # count resets.
        ratelimit_left = int(webhook_post.headers['X-RateLimit-Remaining'])
        ratelimit_wait = int(webhook_post.headers['X-RateLimit-Reset-After'])

        # If there's no posts remaining, we'll wait for the reset.
        if ratelimit_left <= 0:
            logger.info(f'Waiting {ratelimit_wait} seconds to next post...')
            time.sleep(ratelimit_wait)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            global_wait_time = float(e.response.headers['retry-after'])/1000
            logger.warning(f'Global rate limit reached, waiting {global_wait_time} seconds to next post...')
            time.sleep(global_wait_time)
        raise


def get_feeds():
    fin = open("feeds.json")
    ret = json.load(fin)["feeds"]
    fin.close()
    return ret


def get_global_settings():
    fin = open("feeds.json")
    ret = json.load(fin)["global_settings"]
    fin.close()
    return ret


def make_embed(feed, post, first=True, last=True):
    embed = {
      "type": "rich",
      "color": int(feed['color'], 16) if 'color' in feed else 0x000000,
      "image": {
        "url": post['image_url']
      },
    }
    if first:
        embed = {
            "title": f"New post in {feed['name']}",
            "fields": [
                {
                  "name": "Source",
                  "value": f"https://www.pixiv.net/artworks/{post['id']}"
                }
            ],
            "author": {
                "name": post['author_name'],
                "url": f"https://www.pixiv.net/en/users/{post['author_id']}",
                "icon_url": post['author_pfp']
            },
            "url": f"https://www.pixiv.net/en/artworks/{post['id']}",
            **embed,
        }
    if last:
        embed = {
            "footer": {
              "text": f"ID: {post['id']}"
            },
            **embed,
        }
    return {"embeds": [embed]}


def get_last_posted_for(feed_id):
    fin = open("last_posted.json")
    data = json.load(fin)
    fin.close()
    return data[feed_id] if feed_id in data.keys() else None


def set_last_posted_for(feed_id, post_id: int):
    fin = open("last_posted.json")
    data = json.load(fin)
    fin.close()

    data[feed_id] = post_id

    fout = open("last_posted.json", "w")
    fout.write(json.dumps(data))
    fout.close()


def upload_pixiv_img_elsewhere(url):
    """
    As pixiv urls from their API give 403's, I'm forced to upload them elsewhere.
    :param url: the pixiv URL.
    :return:
    """
    try:
        api.download(url, path="pixiv_downloads", name="tmp-image")
        new_url = images.upload_image(os.path.join("pixiv_downloads", "tmp-image"), logger)
        os.remove(os.path.join("pixiv_downloads", "tmp-image"))
        return new_url
    except Exception as exc:
        logger.error(f"Error while downloading image:\n{traceback.format_exc()}")
        return None


def break_post_images(post):
    """
    Turn a Pixiv post into an array of multiple posts with minimal information.
    One image per item.
    :param post: dict
    :return: list<dict>
    """
    # Get the author's profile picture. Usually the keyword is "medium" but I don't want to risk bugs.
    author_pfp = None
    if "medium" in post.user.profile_image_urls:
        author_pfp = post.user.profile_image_urls.medium
    else:
        keys = post.user.profile_image_urls.keys()
        if len(keys) > 0:
            author_pfp = post.user.profile_image_urls[keys[0]]

    author_pfp_url = ""
    if author_pfp:
        author_pfp_url = upload_pixiv_img_elsewhere(author_pfp)

    ret = []
    if len(post.meta_pages) > 0:
        for image in post.meta_pages:
            image_url = upload_pixiv_img_elsewhere(image.image_urls.original)
            if image_url is None:
                return []

            ret.append({
                'id': post.id,
                'author_name': f"{post.user.name} - @{post.user.account}",
                'author_id': post.user.id,
                'author_pfp': author_pfp_url,
                'image_url': image_url
            })
    else:
        image_url = upload_pixiv_img_elsewhere(post.meta_single_page.original_image_url)
        ret.append({
            'id': post.id,
            'author_name': f"{post.user.name} - @{post.user.account}",
            'author_id': post.user.id,
            'author_pfp': author_pfp_url,
            'image_url': image_url
        })

    return ret


def is_blacklisted(post, feed):
    if "is_nsfw" in feed:
        if not feed["is_nsfw"] and post.x_rating != Rating.ALL:
            return "nsfw-in-sfw"

        if feed["is_nsfw"] and feed["only_nsfw"] and post.x_rating == Rating.ALL:
            return "sfw-in-nsfw"

    forbidden_tags = feed['blacklist']['tags'] + global_settings['blacklist']['tags']
    for tag in post.tags:
        if tag.name in forbidden_tags or tag.translated_name in forbidden_tags:
            return "bad-tag"

    if post.user.account in feed['blacklist']['users'] + global_settings['blacklist']['users']:
        return "bad-user"

    return None


@retry(Exception, delay=1, backoff=2, jitter=2, logger=logger)
def get_new_feed_posts(feed):
    global global_settings
    # Refreshes the global settings every loop.
    global_settings = get_global_settings()

    posts = []

    last_known_post_id = get_last_posted_for(feed["id"])
    result = api.search_illust(feed["keyword"])

    if "error" in result:
        api.auth(refresh_token=REFRESH_TOKEN)
        raise TypeError

    first_loop = True
    for entry in result.illusts:
        # Record the newest post
        if first_loop:
            first_loop = False
            set_last_posted_for(feed['id'], entry.id)

        blacklist_reason_id = is_blacklisted(entry, feed)
        if blacklist_reason_id is not None:
            logger.info(f"Post {entry.id} in feed {feed['id']} ({feed['name']}) ignored "
                        f"for reason: {blacklist_reasons[blacklist_reason_id]}.")
            continue

        # If the ID is the same as the last recorded one, there's no new entries
        if entry["id"] == last_known_post_id:
            logger.info(f"No new posts for feed {feed['id']} ({feed['name']}).")
            break

        logger.info(f"Adding post {entry.id} to feed {feed['id']} ({feed['name']}).")
        posts.append(break_post_images(entry))

        # If the ID doesn't exist yet, it's a new feed, so only the first
        # post of the feed will be posted and recorded.
        if last_known_post_id is None:
            logger.info(f"Detected new feed {feed['id']} ({feed['name']}).")
            break

    return posts


def get_embeds(feed, posts):
    """
    Gets a list of simplified dicts from break_post_images and turns them into embeds.
    :param feed: The feed the post will be posted to.
    :param posts: A list of dicts.
    :return: A list of embeds.
    """
    ret = []
    first = True
    for i in range(len(posts)):
        p = posts[i]
        ret.append(make_embed(feed, p, first=(i == 0), last=(i == len(posts)-1)))
        if first:
            first = False
    return ret


def main():
    if not os.path.exists("last_posted.json"):
        last_posted = open("last_posted.json", "w")
        last_posted.write("{}")
        last_posted.close()

    if not os.path.exists("pixiv_downloads"):
        os.mkdir("pixiv_downloads")

    while True:
        feeds = get_feeds()
        for feed in feeds:
            try:
                posts = get_new_feed_posts(feed)
                embeds = []
                for post in posts:
                    embeds += get_embeds(feed, post)
                for e in embeds:
                    make_post(feed, e)
            except Exception as e:
                logger.critical(traceback.format_exc())
        time.sleep(SLEEP_TIME)


if __name__ == '__main__':
    api.auth(refresh_token=REFRESH_TOKEN)
    logger = setup_logger()
    main()



