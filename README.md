# Pixivcord
Pixiv posts to Discord with multiple webhooks.

## Installation
To install and run this bot, first clone this repository.
```bash
git clone https://github.com/SartoRiccardo/pixivcord.git
cd pixivcord
```

Then, install all dependencies needed for the project, listed in `requirements.txt`.
```bash
pip install -r requirements.txt
```

## Configuration
First, rename the `config.example.py` and the `feeds.example.json` to `config.py` and `feeds.json`, respectively
```bash
mv config.example.py config.py
mv feeds.example.json feeds.json
```

### `config.py`
To start this bot, you first need your Pixiv refresh token (which you can get by following the instructions on [this gist](https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362). I've already included the script in this repo).
Then, you need an Imgur Client ID, which you can get by registering to [their website](https://imgur.com/) and creating an application.
```python
REFRESH_TOKEN = "XlHj...IbNw"

# Image upload stuff
IMGUR_CLIENT_ID = "d5c...fa3"
...
```

### `feeds.json`
Follow the examples in `feeds.example.json` to create your own feeds. Here is the list of fields a feed object can have:
| Field name | Description |
| - | - |
| `id` | A unique string. Can be literally anything, as long as no other field has exactly the same one. |
| `name` | The name of the feed, shown as the title of the embed. |
| `keyword` | The keyword that Pixiv will look at for the feed. |
| `webhook` | The URL of the Discord webhook to post Pixiv art to. |
| `blacklist.tags` | feed-specific blacklisted tags. It's recommended to put them in japanese. |
| `blacklist.users` | feed-specific blacklisted usernames. |
| `color` | The color of the Discord embed, in hexadecimal. |
| `is_nsfw` | If set to `true`, the bot will also post images marked as NSFW. |
| `only_nsfw` | If set to `true`, the bot will *only* post images marked as NSFW, ignoring SFW ones. This field is ignored if `is_nsfw` is set to `false`. |

## Changing image hosting websites
Trying to link a Pixiv image url directly gives response code 403, so it will not show on Discord. As a workaround, the bot downloads the image(s)
and reuploads them to an image hosting website (Imgur). If you want to use something different, you can edit the `upload_image` function in
`images.py` (and add any other helper functions you'd like).