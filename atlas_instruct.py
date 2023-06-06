import os
import openai
import json
import re
import concurrent.futures
import time

MAX_RETRIES = 5

def generate_text_files():
    # Read the API key from 'apikey.txt'
    with open('apikey.txt', 'r', encoding='utf-8') as f:
        openai.api_key = f.read().strip()

    # Open the JSONL file and load the topics and subtopics
    with open('topics_subtopics.jsonl', 'r') as f:
        lines = f.readlines()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        tasks = []
        for line in lines:
            topic_data = json.loads(line)
            topic = topic_data["topic"]
            subtopics = topic_data["subtopics"]

            for subtopic in subtopics:
                task = {
                    "topic": topic,
                    "subtopic": subtopic,
                    "retries": MAX_RETRIES
                }
                future = executor.submit(make_request, task)
                tasks.append(future)

        while tasks:
            done, tasks = concurrent.futures.wait(tasks, return_when=concurrent.futures.FIRST_COMPLETED)

            for future in done:
                if future.exception():
                    task = future.result()
                    if task["retries"] > 0:
                        task["retries"] -= 1
                        print(f"Error on topic '{task['topic']}' and subtopic '{task['subtopic']}', retrying. {task['retries']} retries left.")
                        tasks.add(executor.submit(make_request, task))
                    else:
                        print(f"Error on topic '{task['topic']}' and subtopic '{task['subtopic']}', no retries left.")
                else:
                    print(f"Completed topic '{future.result()['topic']}' and subtopic '{future.result()['subtopic']}'.")

def make_request(task):
    topic = task["topic"]
    subtopic = task["subtopic"]
    retries = task["retries"]

    print(f"\nInitiating request for topic '{topic}' and subtopic '{subtopic}' with {retries} retries left.")

    try:
        messages=[
            {"role": "system", "content": f"You are a technical expert on {topic}. Your responses will only be the requested output. Do not number any of the outputs and do not output anything other than the requested format. Ensure each item has content. Do not generate more than one input/output task per line."},
            {"role": "user", "content": f"Given the topic '{topic}' and sub-topic '{subtopic}', generate 10 complex question/answer pairs in the following format and follow the formatting explicitly, do not add or take away anything outside this format. Do not create more than one input/output task: {{'id': 'seed_task_[num]', 'name': 'task_name', 'instruction': 'task_instruction', 'instances': [{{'input': 'task_input', 'output': 'task_output'}}], 'is_classification': true/false}}. Ensure to include 5 non-classification and 5 classification tasks."}
        ]
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=3000  # Adjust this as needed
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
    finally:
        return task

task_id_counter = 0  # Global counter for task IDs

def cleanse_text(line):
    global task_id_counter
    # Removing leading number and period
    clean_line = re.sub(r'^\d+\.\s*', '', line)
    # Using regex to find and replace 'name' with modified 'name'
    match_name = re.search(r"'name': '([^']+)'", clean_line)
    if match_name:
        old_name = match_name.group(1)
        new_name = old_name.lower().replace(' ', '_')
        clean_line = clean_line.replace(old_name, new_name)
    # Replace 'id' with a new one
    match_id = re.search(r"'id': '([^']+)'", clean_line)
    if match_id:
        old_id = match_id.group(1)
        new_id = f'seed_task_{task_id_counter}'
        clean_line = clean_line.replace(old_id, new_id)
        task_id_counter += 1
    return clean_line

def text_to_jsonl(dir_path, output_file):
    files_list = os.listdir(dir_path)
    text_files_list = [file for file in files_list if file.endswith('.txt')]

    with open(output_file, 'w', encoding='utf-8') as jsonl_file:
        for text_file in text_files_list:
            with open(os.path.join(dir_path, text_file), 'r', encoding='utf-8') as f:
                content = f.read().splitlines()  # splitlines() removes newline characters
                cleansed_content = [cleanse_text(line) for line in content if line.strip()]  # ignore empty lines or lines only consisting of whitespace

                for entry in cleansed_content:
                    # Convert the string to valid JSON format
                    valid_json = entry.replace("'", '"')
                    jsonl_file.write(valid_json + "\n")

            os.remove(os.path.join(dir_path, text_file))  # delete the txt file after converting

def main():
    generate_text_files()
    dir_path = 'output/'
    output_file = 'output.jsonl'
    text_to_jsonl(dir_path, output_file)

if __name__ == "__main__":
    main()
