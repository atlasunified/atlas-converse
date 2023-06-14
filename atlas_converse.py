import os
import openai
import json
import jsonlines
import re
import concurrent.futures
import time
import queue
import csv

MAX_RETRIES = 5
MAX_WORKERS = 10  # Maximum number of simultaneous tasks
tasks_dict = {}

def generate_text_files():
    # Read the API key from 'apikey.txt'
    with open('apikey.txt', 'r', encoding='utf-8') as f:
        openai.api_key = f.read().strip()

    # Open the JSONL file and load the topics and subtopics
    with open('topics_subtopics.jsonl', 'r') as f:
        lines = f.readlines()

    tasks = queue.Queue()
    for line in lines:
        topic_data = json.loads(line)
        topic = topic_data["topic"]
        subtopics = topic_data["subtopics"]

        for subtopic in subtopics:
            task = {
                "topic": topic,
                "subtopic": subtopic,
                "retries": MAX_RETRIES,
            }
            # Check if the file for this task already exists
            if not os.path.exists(f'output/{topic}_{subtopic}.txt'):
                tasks.put(task)
            else:
                print(f"Skipping task for topic '{topic}' and subtopic '{subtopic}' as it has already been processed.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(make_request, tasks.get()) for _ in range(min(tasks.qsize(), MAX_WORKERS))]  # Start with min of MAX_WORKERS or tasks.qsize() tasks
        while True:
            done, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)  # Wait for at least one task to complete
            for future in done:
                futures.remove(future)  # Remove completed tasks from futures list
            if tasks.empty() and not futures:  # If no more tasks and all futures are done
                break
            while tasks.qsize() > 0 and len(futures) < MAX_WORKERS:  # If there are tasks left and we haven't reached MAX_WORKERS yet
                futures.append(executor.submit(make_request, tasks.get()))  # Start new tasks

def make_request(task):
    topic = task["topic"]
    subtopic = task["subtopic"]
    retries = task["retries"]

    print(f"\nInitiating request for topic '{topic}' and subtopic '{subtopic}' with {retries} retries left.")

    try:
        messages = [
            {"role": "system", "content": "You are an intellectual conversation bot. Your job is to execute the users requests without responding with any jargon like, 'sure, I can help, what would you like to know'. Your strength is in brevity and answering directly."},
            {"role": "user", "content": f"You will create meaningful conversations between a user and an AI. The conversation length is 3,000 tokens long. The conversation from the user must be complex, at the PhD level in content, and lengthy and the conversation must conclude at the end with an understanding of the topic. Do not deviate from the JSONL format of {json.dumps({'id': 'string', 'conversations': [{'from': 'string', 'value': 'string'}]})} and only create one singular JSONL. The topic is '{topic}' and the subtopic is '{subtopic}'."},
        ]

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=1500,
            temperature=0.8,

        )
        # Prepare the response
        response = f"{completion.choices[0].message['content']}"

        # Output the response to a text file named after the topic and subtopic
        with open(f'output/{topic}_{subtopic}.txt', 'w', encoding='utf-8') as f:
            f.write(response)

        print(f"Successful request for topic '{topic}' and subtopic '{subtopic}'. Writing to file.")
    except Exception as e:
        print(f"Exception occurred for topic '{topic}' and subtopic '{subtopic}'.")
        task["exception"] = e
        if retries > 0:
            print(f"Retrying task for topic '{topic}' and subtopic '{subtopic}', retries left: {retries-1}")
            task["retries"] = retries - 1
            make_request(task)

task_id_counter = 0  # Global counter for task IDs

def text_to_json(dir_path, output_file):
    files_list = os.listdir(dir_path)
    text_files_list = [file for file in files_list if file.endswith('.txt')]

    all_conversations = []
    id_counter = 1

    for text_file in text_files_list:
        file_path = os.path.join(dir_path, text_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                json_content = json.loads(content)
                json_content["id"] = str(id_counter)  # renumbering the id
                all_conversations.append(json_content)
                id_counter += 1
        except json.JSONDecodeError:
            print(f"Error decoding JSON for file: {text_file}. Deleting the file.")
            os.remove(file_path)  # Deletes the file

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_conversations, f, indent=4)

def main():
    generate_text_files()
    dir_path = 'output/'
    output_file = 'combined-convo.json'
    text_to_json(dir_path, output_file)

    # Check if all files are in the output
    if not os.path.isfile(output_file):
        print(f"Output file {output_file} does not exist.")
    else:
        print(f"Output file {output_file} is successfully written.")

if __name__ == "__main__":
    main()