import sqlite3
import os

def clear_task_history():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gridmind.db")
    
    if not os.path.exists(db_path):
        print(f"Error: Could not find database at {db_path}")
        return

    print(f"Connecting to database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tables exist before attempting to clear them
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        has_tasks = cursor.fetchone()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dispatch_log'")
        has_log = cursor.fetchone()

        if has_tasks:
            cursor.execute("DELETE FROM tasks")
            print(f"Cleared {cursor.rowcount} tasks from the history.")
            
        if has_log:
            cursor.execute("DELETE FROM dispatch_log")
            print(f"Cleared {cursor.rowcount} dispatch logs.")

        conn.commit()
        print("\nSuccess! The task history has been completely cleared for your demo.")
        print("Your dashboard should now show zero failed tasks.")
        
    except sqlite3.Error as e:
        print(f"Database error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    clear_task_history()
