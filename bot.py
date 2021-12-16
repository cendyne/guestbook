import os
import traceback
import sys
import uuid
import time
import logging
from typing import Dict, List, Text, Tuple, Union
from telegram.ext import Updater, InlineQueryHandler, CommandHandler, CallbackContext, ChatMemberHandler, MessageHandler, Filters, CallbackQueryHandler
from telegram import Update, InlineQueryResultCachedSticker, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

import guestbookdb

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


load_dotenv()


token = os.environ["BOT_TOKEN"]
icon_path = os.environ["ICON_PATH"]
admin = int(os.getenv("ADMIN"))


@guestbookdb.with_connection
def start(update: Update, _: CallbackContext) -> None:
    print(update)
    update.message.reply_text("Hey there, what letters and numbers do you see on screen?")


def downloadIconForUser(c: CallbackContext, user_id: int) -> Union[Text, None]:
    photos = c.bot.get_user_profile_photos(user_id, limit = 1)
    size = 0
    photo_to_use = None
    photo_id = None
    photo_ending = None
    if not photos is None:
        pictures = photos.photos
        if pictures and len(pictures) > 0:
            first_photo = pictures[0]
            if first_photo and len(first_photo):
                photo = first_photo[0]
                if photo.height > size:
                    photo_to_use = photo.file_id
                    photo_id = photo.file_unique_id
                    size = photo.height
    if photo_to_use:
        photo_ending = photo_id + ".jpg"
        path = icon_path + "/" + photo_ending
        if not os.path.exists(path):
            file = c.bot.get_file(photo_to_use)
            if not os.path.exists(icon_path):
                os.makedirs(icon_path)
            file.download(custom_path=path)
        return photo_ending
    return None

@guestbookdb.with_connection
def messageHandler(update: Update, c: CallbackContext) -> None:
    print(update)
    user = update.message.from_user
    icon = None
    updated_icon = False
    guestbook_user = guestbookdb.find_user(user.id)
    if guestbook_user:
        icon = guestbook_user.icon
        if icon is None:
            icon = downloadIconForUser(c, user.id)
            if not icon is None:
                guestbookdb.update_user_icon(user.id, icon)
                updated_icon = True
    else:
        icon = downloadIconForUser(c, user.id)
        guestbookdb.add_user(user.id, user.first_name, user.last_name, user.username, icon)
        updated_icon = True
    identity = guestbookdb.find_unlinked_challenge(update.message.text)
    if identity is None:
        update.message.reply_text("Sorry, I do not recognize that. Please check the website and try again.")
    else:
        guestbookdb.challenge_link_to_user(identity, user.id)
        # Set expiration to 1 month from now
        guestbookdb.update_challenge_expires(identity, int(time.time() + 60 * 60 * 24 * 30))
        update.message.reply_text("Got it! Please return to the website")
        # Also update the icon in case it's a re-auth
        if not updated_icon:
            downloaded = downloadIconForUser(c, user.id)
            if icon != downloaded:
                guestbookdb.update_user_icon(user.id, downloaded)



def main() -> None:
    guestbookdb.init()
    # Create the Updater and pass it your bot's token.
    updater = Updater(token)

    guestbookdb.set_config("username", updater.bot.username)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start))

    # on non command i.e message - echo the message on Telegram
    dispatcher.add_handler(MessageHandler(Filters.all, messageHandler))

    # for [id, name, file_id] in yelldb.findAllPending():
    #   updater.bot.send_document(
    #       chat_id=review_chan,
    #       document=file_id,
    #       reply_markup=InlineKeyboardMarkup([
    #          [InlineKeyboardButton(name, callback_data="YES " + id)],
    #          [InlineKeyboardButton("\u274C", callback_data="NO " + id)]
    #       ]))

    # Start the Bot
    updater.start_polling()

    # Block until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
