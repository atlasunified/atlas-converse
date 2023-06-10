import os
import openai
import json
import re
import concurrent.futures
import time
import queue

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
        if retries > 0:
            print(f"Retrying task for topic '{topic}' and subtopic '{subtopic}', retries left: {retries-1}")
            task["retries"] = retries - 1
            make_request(task)

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

            # os.remove(os.path.join(dir_path, text_file))  # delete the txt file after converting

def main():
    generate_text_files()
    dir_path = 'output/'
    output_file = 'output.jsonl'
    text_to_jsonl(dir_path, output_file)

    # Check if all tasks are done
    not_done = [task for task, done in tasks_dict.items() if not done]
    if not_done:
        print(f"Following tasks were not completed: {not_done}")
    else:
        print("All tasks have been completed successfully.")

    # Check if all files are in the output
    for task in tasks_dict.keys():
        if not os.path.isfile(f"{dir_path}{task}.txt"):
            print(f"Output file for task {task} does not exist.")
        else:
            print(f"Output file for task {task} is successfully written.")

if __name__ == "__main__":
    main()