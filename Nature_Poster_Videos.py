"""
Author: Logan Maupin
Date: 10/07/2022

Description:
This program's purpose is to call Pexels' API, grab a list of videos
given specific search keywords, then iterate through that list to
see if it matches specific criteria for posting. Once we find
one that we can use, we will post it to FB, edit a caption to the post
that we just made, then log the details of what we posted to a Google
sheets spreadsheet so that we don't post it again.
Some features of this script include: list comprehension, image hashing,
optical character recognition, three different APIs, json parsing, and more.
"""
import config  # used to get the secret sensitive info needed for our APIs - not uploaded to GitHub for security purposes
import requests  # needed to get image file size before we download images (to make sure we don't download images too large that we can't upload elsewhere).
import os  # needed to get the file paths
import random  # Used to pick a random keyword to search when grabbing a video
from pexels_api import API  # need this to get images to use from Pexels (our source of images for the project)
from datetime import datetime  # used for date and time in the FB log posting, so we know when things were posted to FB
import facebook  # to add captions and comments to existing posts.
import json  # to decipher the dictionary we get back in return from FB servers. (Mainly this is used to edit captions to the posts).
import sqlite3  # our database access, where all the posts get logged to, a local DB file on the Raspberry Pi.


def no_badwords(sentence: list[str]):
    """
    This function checks a list of strings to see if there is a bad word in the given list of strings.

    :param sentence: This is any list of strings you wish to check for bad words in.
    :returns:  Returns True if there is no bad-word in the given sentence list of strings, false otherwise.
    """
    cursor.execute('SELECT * FROM Bad_Words')
    Bad_Words_from_DB = cursor.fetchall()
    Bad_Words_List = [item for word in Bad_Words_from_DB for item in word]

    for word in sentence:
        word.lower()

    return not any(word in sentence for word in Bad_Words_List)


def get_file_size(url):
    """
    Gets file size of an image given the url for it.

    :param url: This is any url of an image that you wish to get the file size of.
    :returns: File size of an image as a floating point number.
    """

    # grabbing data from our selected url
    requests_content_length = requests.get(url)

    # divides file size by 1000, so we can get how many kilobytes it is
    length = float(requests_content_length.headers.get('content-length')) / 1000

    return length


def acceptable_extension(video_extension):
    """
    This function defines the list of acceptable video extensions
    we can use. It also tells us whether the one we want to use is
    in the acceptable list of extensions.
    :param video_extension: The end of an image url of an image hosted online.
    :returns: True / False of whether the video extension matches an
    acceptable format.
    """

    extensions = ['mp4', 'mov', 'wmv', 'avi']
    return any(extensions in video_extension for extensions in extensions)


def post_to_fb(video_link):
    """
    This function posts to fb given a specific video.url that
    you wish to use.
    :param video_link: any url of a pexels video, must end in .mp4 or something similar.
    :returns: response from FB servers with the post id or an error
    """

    fb_page_id = "101111365975816"
    post_url = f'https://graph-video.facebook.com/v15.0/{fb_page_id}/videos'
    payload = {
        "url": video_link,
        "access_token": config.config_stuff['FB_Access_Token']
    }

    post_to_fb_request = requests.post(post_url, data=payload)
    return post_to_fb_request.text


def get_post_id_from_json(request):
    """
    This function takes the response from FB servers and parses out
    the post ID from it.
    :param request: json response object from FB
    :returns: post id string
    """

    return_text_dict = json.loads(request)
    id_from_json = return_text_dict.get('id')

    if id_from_json:
        return id_from_json

    else:
        return None


def edit_fb_post_caption(post_id, video_description, video_permalink):
    """
    This function takes a given FB post and edits a caption to it.

    :param post_id: any FB post you wish to edit.
    :param video_description: what you wish to edit to it, preferably a str type
    :param video_permalink: the link of the original pexels video for credit
    :returns: None
    """

    fb_page_id = "101111365975816"
    GitHub_Link = 'https://github.com/Voltaic314/Nature-Poster'

    # define fb variable for next line with our access info
    fb = facebook.GraphAPI(access_token=config.config_stuff['FB_Access_Token'])

    # edit caption of existing fb post we just made
    fb.put_object(parent_object=f'{fb_page_id}_{post_id}', connection_name='',
                  message=f'Description: {video_description}\n\nPexels image link: {video_permalink}\n\n'
                          f'P.S. This Facebook post was created by a bot. To learn more about how it works,'
                          f' check out the GitHub page here: {GitHub_Link}')

    print("Caption has been edited to post successfully.")


def id_is_in_db(table, id_string):
    """
    The purpose of this function is to check if the video ID we have is in our database or not.
    :param table: Which DB table we want to look through to see if the ID is in there.
    :param id_string: The ID of the video returned by Pexels API (the video.id object value)
    :returns: True if the video ID is in the DB, else, false.
    """

    cursor.execute(f'SELECT ID FROM {table} WHERE ID="{id_string}"')

    IDs_from_db = cursor.fetchall()

    if IDs_from_db:
        return True

    else:
        return False


def get_search_terms():
    """
    This function gets the search terms from the search terms table in the DB. It will return a list of search term
    that we can use for the keyword searches. In reality, we will pick a random one from this 1d array that it returns.
    :returns: 1 dimensional list containing a list of strings that represent our search terms to be used later.
    """

    cursor.execute('Select * FROM Photo_Search_Terms')
    Search_Terms_from_DB = cursor.fetchall()

    return [item for word in Search_Terms_from_DB for item in word]


def log_to_DB(formatted_tuple: tuple):
    """
    The purpose of this function is to log our grabbed info from the get_video function over to the database
    :param formatted_tuple: tuple containing the info that the user wishes to log to the database
    :returns: None
    """
    cursor.execute('INSERT INTO Nature_Bot_Logged_FB_Posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', formatted_tuple)


def process_videos(videos):
    """
    This is the function that primarily makes decisions with the videos.
    It goes through a series of if statements to figure out if the video
    is worth posting to FB or not based on a given criteria below.
    :param videos: list of videos to iterate through, retrieved from
    the next function below.
    :returns: Spreadsheet values to send, this will evaluate to True and allow
    the code to stop running once the post has been logged to the spreadsheet.
    """
    data_to_log = []

    for video in videos:
        video_description = video.description
        video_user = video.videographer
        video_id = str(video.id)
        video_permalink = video.url
        video_extension = video.extension
        video_link = video.link
        video_file_size = get_file_size(video.url)

        if not acceptable_extension(video_extension):
            continue

        if id_is_in_db('Nature_Bot_Logged_FB_Posts', str(video.id)):
            continue

        # make sure the file size is less than 1 GB. (This is primarily for FB posting limitations).
        if video_file_size >= 1_000_000:
            continue

        # If the video is greater than 20 minutes long, start over. (also for FB Positing limitations)
        if video.duration >= 1200:
            continue

        if not no_badwords(video_description.lower().split(" ")):
            continue

        post_to_fb_request = post_to_fb(video_link)
        fb_post_id = get_post_id_from_json(post_to_fb_request)
        successful_post = fb_post_id in post_to_fb_request

        if not successful_post:
            continue

        else:

            print("Photo was posted to FB")

            dt_string = str(datetime.now().strftime("%m/%d/%Y %H:%M:%S"))

            edit_fb_post_caption(fb_post_id, video_description, video_permalink)

            print("Caption has been edited successfully.")

            data_to_log = (
                dt_string, str(post_to_fb_request), str(video_description), str(video_user),
                str(video_id), str(video_permalink), str(video.url), str(video_link),
                float(video_file_size),
            )

            log_to_DB(data_to_log)

            print("Data has been logged to the database. All done!")

            connect.commit()
            connect.close()

            break

    return data_to_log


def main():
    """
    This function does the actual searching of the videos.
    This function calls Pexels' API and pulls a list of videos
    to search through. If none of the videos meet our criteria,
    then load the "next page" which is just another list of 15 videos
    to search through.
    :returns: None
    """

    global done, connect, cursor
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(BASE_DIR, "Nature_Bot_Data.db")
    connect = sqlite3.connect(db_path)
    cursor = connect.cursor()
    PEXELS_API_KEY = config.config_stuff3['PEXELS_API_KEY']
    api = API(PEXELS_API_KEY)
    Search_Terms = get_search_terms()  # list of art sources to use from Pexels
    api.search_video(str(random.choice(Search_Terms)), page=1, results_per_page=15)

    done = False
    while not done:
        done = process_videos(videos=api.get_video_entries())
        if not done:
            api.search_next_page()


if __name__ == "__main__":
    main()
