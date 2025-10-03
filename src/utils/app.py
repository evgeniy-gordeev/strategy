from flask import Flask, request, jsonify, render_template
import subprocess
import os
import threading
import time

app = Flask(__name__)

process = None
log_file_path = './xyz415.log'

def read_logs_from_file():
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-50:] if line.strip()]
    except FileNotFoundError:
        return ['Лог-файл пока не создан']
    except Exception as e:
        return [f'Ошибка чтения логов: {str(e)}']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    global process
    if process is not None:
        return jsonify({'error': 'Скрипт уже запущен'}), 400
    
    data = request.json
    deposit = data.get('deposit')
    
    if not deposit:
        return jsonify({'error': 'Необходимо указать депозит'}), 400
              
    try:
        process = subprocess.Popen(
            ['python3', 'xyz415.py'],
            env={
                **os.environ,
                'DEPOSIT': str(deposit),
                'PYTHONUNBUFFERED': '1'
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        threading.Thread(
            target=lambda: [print(line.strip()) for line in iter(process.stdout.readline, '')],
            daemon=True
        ).start()
        
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} - INFO - Скрипт запущен\n')
        return jsonify({'message': 'Скрипт запущен'})
    except Exception as e:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} - ERROR - Не удалось запустить скрипт: {str(e)}\n')
        return jsonify({'error': str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop():
    global process
    if process is None:
        return jsonify({'error': 'Скрипт не запущен'}), 400
    
    try:
        process.terminate()
        process.wait()
        process = None
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} - INFO - Скрипт остановлен\n')
        return jsonify({'message': 'Скрипт остановлен'})
    except Exception as e:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} - ERROR - Не удалось остановить скрипт: {str(e)}\n')
        return jsonify({'error': str(e)}), 500

@app.route('/toggle_check', methods=['POST'])
def toggle_check():
    data = request.json
    check_enabled = data.get('check_enabled')
    
    if check_enabled is None:
        return jsonify({'error': 'Необходимо указать состояние проверки'}), 400
    
    try:
        os.environ['CHECK_ENABLED'] = '1' if check_enabled else '0'
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} - INFO - Проверка {"включена" if check_enabled else "отключена"}\n')
        return jsonify({'message': f'Проверка {"включена" if check_enabled else "отключена"}'})
    except Exception as e:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} - ERROR - Не удалось изменить состояние проверки: {str(e)}\n')
        return jsonify({'error': str(e)}), 500

@app.route('/logs', methods=['GET'])
def get_logs():
    return jsonify({'logs': read_logs_from_file()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)