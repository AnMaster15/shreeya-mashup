# app.py
from flask import Flask, render_template, request
from googleapiclient.discovery import build
import yt_dlp
import os
from moviepy.editor import AudioFileClip, concatenate_audioclips
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
from typing import List
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# YouTube API function
def get_youtube_links(query: str, max_results: int = 2) -> List[str]:
    api_key = os.getenv('YOUTUBE_API_KEY')
    youtube = build('youtube', 'v3', developerKey=api_key)
    search_response = youtube.search().list(
        q=query,
        part='snippet',
        type='video',
        maxResults=max_results
    ).execute()

    video_links = []
    for item in search_response['items']:
        video_id = item['id']['videoId']
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        video_links.append(video_url)

    return video_links

# Download audio function
def download_audio(video_urls: List[str], download_path: str) -> List[str]:
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{download_path}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    downloaded_files = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(video_urls)
        for url in video_urls:
            info_dict = ydl.extract_info(url, download=False)
            filename = ydl.prepare_filename(info_dict)
            mp3_file = filename.rsplit('.', 1)[0] + '.mp3'
            downloaded_files.append(mp3_file)

    return downloaded_files

# Create mashup function
def create_mashup(audio_files: List[str], duration_sec: int, output_file: str) -> str:
    clips = []
    for file in audio_files:
        clip = AudioFileClip(file)
        clip_duration = min(duration_sec, clip.duration)
        clips.append(clip.subclip(0, clip_duration))
        logging.info(f"Added clip from {file} with duration {clip_duration} seconds")

    final_clip = concatenate_audioclips(clips)
    final_clip.write_audiofile(output_file)
    logging.info(f"Mashup created successfully and saved to {output_file}")
    return output_file

# Send email function
def send_email_with_attachment(recipient_email: str, subject: str, body: str, file_path: str) -> None:
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    if os.path.exists(file_path):
        with open(file_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(file_path)}")
        msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient_email, text)
        logging.info("Email sent successfully!")
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        raise
    finally:
        server.quit()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            singer_name = request.form['singer_name']
            num_videos = int(request.form['num_videos'])
            trim_duration = int(request.form['trim_duration'])  # In seconds
            email = request.form['email']

            logging.info(f"Received request: Singer: {singer_name}, Videos: {num_videos}, Duration: {trim_duration}, Email: {email}")

            # Get YouTube links
            video_links = get_youtube_links(singer_name, num_videos)
            logging.info(f"Found {len(video_links)} video links")

            # Download audio
            download_path = "temp_audio"
            downloaded_files = download_audio(video_links, download_path)
            logging.info(f"Downloaded {len(downloaded_files)} audio files")

            # Create mashup
            output_file = "mashup.mp3"
            mashup_file = create_mashup(downloaded_files, trim_duration, output_file)

            # Send email
            subject = "Your Requested Audio Mashup"
            body = "Hello,\n\nPlease find the requested audio mashup attached to this email."

            send_email_with_attachment(email, subject, body, mashup_file)

            return "Mashup created and sent to your email successfully!"
        except Exception as e:
            logging.error(f"Error occurred: {e}")
            return f"An error occurred: {str(e)}", 500

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)