#!/usr/bin/env python3
import json
import logging
import os
import signal
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from local_file_picker import local_file_picker
from nicegui import ui

# Setup logging for service mode
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('sync_service.log', encoding='utf-8')
    ]
)

# Get the directory where the executable or script is located
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    app_dir = Path(sys.executable).parent
else:
    # Running as script
    app_dir = Path(__file__).parent

TASKS_FILE = app_dir / 'sync_tasks.json'


class TaskManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.active_tasks = set()
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.load_and_start_tasks()
            self._initialized = True
    
    def load_tasks(self):
        if not TASKS_FILE.exists():
            return []
        
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
            
            # Migrate old tasks
            for task in tasks:
                if 'id' not in task:
                    task['id'] = str(uuid.uuid4())
                if 'is_template' not in task:
                    task['is_template'] = False
                if 'last_ran' not in task:
                    task['last_ran'] = None
            
            self.save_tasks(tasks)
            return tasks
        except Exception as e:
            logging.error(f"Error loading tasks: {e}")
            return []
    
    def save_tasks(self, tasks):
        try:
            # Ensure the directory exists
            TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(tasks, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving tasks: {e}")
    
    def add_task(self, task_data):
        tasks = self.load_tasks()
        tasks.append(task_data)
        self.save_tasks(tasks)
    
    def remove_task(self, task_id):
        tasks = self.load_tasks()
        tasks = [t for t in tasks if t.get('id') != task_id]
        self.save_tasks(tasks)
        self.active_tasks.discard(task_id)
    
    def update_task(self, task_id, updates):
        tasks = self.load_tasks()
        for task in tasks:
            if task.get('id') == task_id:
                task.update(updates)
                break
        self.save_tasks(tasks)
    
    def sync_files(self, source_path, dest_path):
        try:
            source = Path(source_path)
            dest = Path(dest_path)
            
            logging.info(f"Starting sync: {source} -> {dest}")
            
            # Reset counters
            self.copied_count = 0
            self.skipped_count = 0
            self.error_count = 0
            self.error_files = []
            
            if source.is_file():
                self._sync_file(source, dest / source.name)
            else:
                self._sync_directory(source, dest / source.name)
            
            logging.info(f"Sync completed - Copied: {self.copied_count}, Identical: {self.skipped_count}, Errors: {self.error_count}")
            
            if self.error_files:
                logging.warning("Files with errors:")
                for error_file in self.error_files:
                    logging.warning(f"  - {error_file}")
        except Exception as e:
            logging.error(f"Sync failed: {e}")
    
    def _sync_file(self, source: Path, dest: Path):
        try:
            if not dest.exists() or source.stat().st_mtime > dest.stat().st_mtime:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                self.copied_count += 1
            else:
                self.skipped_count += 1
        except PermissionError:
            self.error_count += 1
            self.error_files.append(f"{source.name} (Access denied)")
        except Exception as e:
            self.error_count += 1
            self.error_files.append(f"{source.name} ({e})")
    
    def _sync_directory(self, source: Path, dest: Path):
        dest.mkdir(parents=True, exist_ok=True)
        
        for item in source.rglob('*'):
            if item.is_file():
                try:
                    relative_path = item.relative_to(source)
                    dest_file = dest / relative_path
                    
                    if not dest_file.exists() or item.stat().st_mtime > dest_file.stat().st_mtime:
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest_file)
                        self.copied_count += 1
                    else:
                        self.skipped_count += 1
                except PermissionError:
                    self.error_count += 1
                    self.error_files.append(f"{item.relative_to(source)} (Access denied)")
                except Exception as e:
                    self.error_count += 1
                    self.error_files.append(f"{item.relative_to(source)} ({e})")
    
    def run_task(self, task):
        task_id = task.get('id')
        
        if task_id in self.active_tasks:
            return
        
        self.active_tasks.add(task_id)
        
        if task.get('is_repeat'):
            self._run_repeat_task(task)
        else:
            self._run_one_time_task(task)
    
    def _run_repeat_task(self, task):
        task_id = task['id']
        scheduled_time = datetime.fromisoformat(task['scheduled_datetime']).time()
        
        while True:
            now = datetime.now()
            today = now.date()
            next_run = datetime.combine(today, scheduled_time)
            
            if next_run <= now:
                next_run = datetime.combine(today + timedelta(days=1), scheduled_time)
            
            wait_seconds = (next_run - now).total_seconds()
            logging.info(f"Next sync in {int(wait_seconds)}s at {next_run.strftime('%Y-%m-%d %H:%M')}")
            
            time.sleep(wait_seconds)
            logging.info(f"Running repeat sync: {task['source_path']}")
            
            self.sync_files(task['source_path'], task['destination_path'])
            
            # Update last_ran and next scheduled_datetime
            next_scheduled = next_run + timedelta(days=1)
            self.update_task(task_id, {
                'last_ran': datetime.now().isoformat(),
                'scheduled_datetime': next_scheduled.isoformat()
            })
    
    def _run_one_time_task(self, task):
        scheduled_datetime = datetime.fromisoformat(task['scheduled_datetime'])
        now = datetime.now()
        
        if scheduled_datetime > now:
            wait_seconds = (scheduled_datetime - now).total_seconds()
            logging.info(f"Waiting {int(wait_seconds)}s for scheduled sync")
            time.sleep(wait_seconds)
        
        logging.info(f"Running scheduled sync: {task['source_path']}")
        self.sync_files(task['source_path'], task['destination_path'])
        
        self.update_task(task['id'], {'last_ran': datetime.now().isoformat()})
        self.remove_task(task['id'])
    
    def load_and_start_tasks(self):
        tasks = self.load_tasks()
        
        for task in tasks:
            if task.get('is_template'):
                continue
            
            task_id = task.get('id')
            if task_id in self.active_tasks:
                continue
            
            if task.get('is_repeat'):
                # Update repeat task to next valid time
                original_time = datetime.fromisoformat(task['scheduled_datetime']).time()
                today = date.today()
                next_run = datetime.combine(today, original_time)
                
                if next_run <= datetime.now():
                    next_run = datetime.combine(today + timedelta(days=1), original_time)
                
                self.update_task(task_id, {'scheduled_datetime': next_run.isoformat()})
                task['scheduled_datetime'] = next_run.isoformat()
                
                logging.info(f"Scheduling repeat task: {task['source_path']} at {next_run.strftime('%Y-%m-%d %H:%M')}")
            else:
                scheduled_datetime = datetime.fromisoformat(task['scheduled_datetime'])
                if scheduled_datetime <= datetime.now():
                    logging.info(f"Removing old task: {task['source_path']}")
                    self.remove_task(task_id)
                    continue
                
                logging.info(f"Scheduling task: {task['source_path']} at {scheduled_datetime.strftime('%Y-%m-%d %H:%M')}")
            
            thread = threading.Thread(target=self.run_task, args=(task,), daemon=True)
            thread.start()


class SyncDialog(ui.dialog):
    def __init__(self):
        super().__init__()
        self.task_manager = TaskManager()
        self.source_path = None
        self.destination_path = None
        
        with self:
            with ui.card():
                ui.label('File Sync').classes('text-h6')
                
                # Source selection
                with ui.row():
                    ui.label('Source:').classes('w-20')
                    self.source_label = ui.label('Not selected').classes('flex-1')
                    ui.button('Browse', on_click=self.select_source)
                
                # Destination selection
                with ui.row():
                    ui.label('Destination:').classes('w-20')
                    self.dest_label = ui.label('Not selected').classes('flex-1')
                    ui.button('Browse', on_click=self.select_destination)
                
                # Run mode toggle
                self.run_mode = ui.toggle(['Run Now', 'Schedule'], value='Run Now')
                
                # Schedule options
                with ui.column() as self.schedule_row:
                    with ui.row():
                        self.year_select = ui.select([2024, 2025, 2026], value=datetime.now().year).props('dense')
                        self.month_select = ui.select(list(range(1, 13)), value=datetime.now().month).props('dense')
                        self.day_select = ui.select(list(range(1, 32)), value=datetime.now().day).props('dense')
                    
                    with ui.row():
                        self.hour_select = ui.select(list(range(24)), value=datetime.now().hour).props('dense')
                        self.minute_select = ui.select(list(range(60)), value=datetime.now().minute).props('dense')
                    
                    self.repeat_checkbox = ui.checkbox('Repeat daily')
                
                # Save task option
                self.save_task_checkbox = ui.checkbox('Save task')
                
                # Buttons
                with ui.row():
                    ui.button('Cancel', on_click=self.close).props('outline')
                    ui.button('Apply', on_click=self.start_sync).props('color=primary')
        
        self.run_mode.on('update:model-value', self._toggle_schedule_visibility)
        self._toggle_schedule_visibility()
    
    def _toggle_schedule_visibility(self):
        visible = self.run_mode.value == 'Schedule'
        self.schedule_row.set_visibility(visible)
    
    async def select_source(self):
        import platform
        root = 'C:\\' if platform.system() == 'Windows' else '/'
        result = await local_file_picker(root)
        if result:
            self.source_path = result[0] if isinstance(result, list) else result
            self.source_label.text = Path(self.source_path).name
    
    async def select_destination(self):
        import platform
        root = 'C:\\' if platform.system() == 'Windows' else '/'
        result = await local_file_picker(root)
        if result:
            self.destination_path = result[0] if isinstance(result, list) else result
            self.dest_label.text = Path(self.destination_path).name
    
    def start_sync(self):
        if not self.source_path or not self.destination_path:
            ui.notify('Please select both source and destination', type='warning')
            return
        
        self.close()
        
        if self.run_mode.value == 'Run Now':
            ui.notify('Sync started')
            threading.Thread(
                target=self.task_manager.sync_files,
                args=(self.source_path, self.destination_path),
                daemon=True
            ).start()
            
            if self.save_task_checkbox.value:
                self._save_template()
        else:
            self._schedule_sync()
    
    def _save_template(self):
        task_data = {
            'id': str(uuid.uuid4()),
            'source_path': self.source_path,
            'destination_path': self.destination_path,
            'scheduled_datetime': datetime.now().isoformat(),
            'is_repeat': False,
            'is_template': True,
            'last_ran': None
        }
        self.task_manager.add_task(task_data)
        ui.notify('Task template saved')
    
    def _schedule_sync(self):
        scheduled_datetime = datetime(
            self.year_select.value,
            self.month_select.value,
            self.day_select.value,
            self.hour_select.value,
            self.minute_select.value
        )
        
        if scheduled_datetime <= datetime.now():
            ui.notify('Please select a future time', type='warning')
            return
        
        task_data = {
            'id': str(uuid.uuid4()),
            'source_path': self.source_path,
            'destination_path': self.destination_path,
            'scheduled_datetime': scheduled_datetime.isoformat(),
            'is_repeat': self.repeat_checkbox.value,
            'is_template': False,
            'last_ran': None
        }
        
        should_save = (
            self.save_task_checkbox.value or
            self.repeat_checkbox.value or
            scheduled_datetime > datetime.now()
        )
        
        if should_save:
            self.task_manager.add_task(task_data)
        
        if self.repeat_checkbox.value:
            ui.notify(f'Daily sync scheduled for {scheduled_datetime.strftime("%H:%M")}')
        else:
            ui.notify(f'Sync scheduled for {scheduled_datetime.strftime("%m/%d %H:%M")}')
        
        threading.Thread(target=self.task_manager.run_task, args=(task_data,), daemon=True).start()


async def open_sync_dialog():
    SyncDialog().open()


@ui.page('/')
def index():
    ui.button('Sync Files', on_click=open_sync_dialog, icon='sync')


# Signal handler for graceful shutdown
def signal_handler(signum, frame):
    logging.info("Received shutdown signal, stopping gracefully...")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Initialize task manager on startup
logging.info("Starting local-synk sync service...")
TaskManager()

try:
    ui.run(reload=False, show=False)
except KeyboardInterrupt:
    logging.info("Service stopped by user")
except Exception as e:
    logging.error(f"Service error: {e}")
finally:
    logging.info("Service shutdown complete")
