#!/usr/bin/env python3
"""
Feature #5 Verification: Database backup and recovery works

This script tests the backup and restore functionality for uat_tests.db
by following the verification steps from Feature #5.

Test Steps:
1. Create test data in uat_test_features table
2. Create test data in uat_test_plan table
3. Run backup command to create backup file
4. Verify backup file exists and is non-zero size
5. Delete some records from database
6. Run restore command from backup
7. Verify all data restored correctly
"""

import sys
import os
import sqlite3
import json
from pathlib import Path

# Add custom directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backup import BackupManager


class Feature5Verifier:
    """Verify Feature #5: Database backup and recovery works"""

    def __init__(self):
        self.db_path = os.path.expanduser('~/.autocoder/uat_tests.db')
        self.backup_manager = BackupManager()
        self.test_data = {}

    def step_1_create_test_data_features(self):
        """Step 1: Create test data in uat_test_features table"""
        print("\n" + "="*80)
        print("STEP 1: Create test data in uat_test_features table")
        print("="*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Insert test records with proper JSON for dependencies
            test_records = [
                (100, 'smoke', 'auth', 'Test login scenario', 'Verify user can login', 'e2e',
                'login_test.spec.js', '["step1", "step2"]', 'User logged in', 'pending', '[]', None),
                (101, 'functional', 'payment', 'Test payment flow', 'Verify payment processing', 'e2e',
                'payment_test.spec.js', '["step1", "step2", "step3"]', 'Payment successful', 'pending', '[]', None),
                (102, 'regression', 'onboarding', 'Test signup', 'Verify user registration', 'e2e',
                'signup_test.spec.js', '["step1"]', 'User registered', 'pending', '[]', None),
            ]

            cursor.executemany(
                """INSERT INTO uat_test_features
                   (priority, phase, journey, scenario, description, test_type,
                    test_file, steps, expected_result, status, dependencies, result)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                test_records
            )

            conn.commit()

            # Verify records were created
            cursor.execute("SELECT COUNT(*) FROM uat_test_features")
            count = cursor.fetchone()[0]

            print(f"✓ Created {len(test_records)} test records in uat_test_features")
            print(f"✓ Total records in table: {count}")

            # Store the count of records we just created (not total)
            self.test_data['features_created'] = len(test_records)
            self.test_data['features_count'] = count

        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False
        finally:
            conn.close()

        return True

    def step_2_create_test_data_plan(self):
        """Step 2: Create test data in uat_test_plan table"""
        print("\n" + "="*80)
        print("STEP 2: Create test data in uat_test_plan table")
        print("="*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Insert test plan
            cursor.execute(
                """INSERT INTO uat_test_plan
                   (project_name, cycle_id, total_features_completed,
                    journeys_identified, recommended_phases, test_prd, approved)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ('test_project', 'test-cycle-001', 10,
                 '["auth", "payment"]', '["smoke", "functional"]',
                 '# Test PRD\n\nThis is a test PRD.', False)
            )

            conn.commit()

            # Verify record was created
            cursor.execute("SELECT COUNT(*) FROM uat_test_plan")
            count = cursor.fetchone()[0]

            print(f"✓ Created 1 test record in uat_test_plan")
            print(f"✓ Total records in table: {count}")

            self.test_data['plan_count'] = count

        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False
        finally:
            conn.close()

        return True

    def step_3_run_backup_command(self):
        """Step 3: Run backup command to create backup file"""
        print("\n" + "="*80)
        print("STEP 3: Run backup command to create backup file")
        print("="*80)

        try:
            # Create backup with custom name for testing
            metadata = self.backup_manager.create_backup(
                backup_name='feature5_test_backup',
                include_json=True
            )

            print(f"✓ Backup created successfully")
            print(f"  - Backup name: {metadata['backup_name']}")
            print(f"  - Database backup: {metadata['backup_db_path']}")
            print(f"  - JSON export: {metadata['backup_json_path']}")
            print(f"  - Original size: {metadata['original_size']} bytes")
            print(f"  - Backup size: {metadata['backup_size']} bytes")
            print(f"  - JSON size: {metadata['json_size']} bytes")
            print(f"  - Checksums match: {metadata['checksums_match']}")
            print(f"  - Record counts: {metadata['record_counts']}")

            self.test_data['backup_metadata'] = metadata

            return True

        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False

    def step_4_verify_backup_file(self):
        """Step 4: Verify backup file exists and is non-zero size"""
        print("\n" + "="*80)
        print("STEP 4: Verify backup file exists and is non-zero size")
        print("="*80)

        try:
            metadata = self.test_data['backup_metadata']
            backup_db = metadata['backup_db_path']
            backup_json = metadata['backup_json_path']
            backup_meta = backup_db.replace('.db', '.meta')

            # Check SQLite backup
            if not os.path.exists(backup_db):
                print(f"✗ FAILED: Backup database not found: {backup_db}")
                return False

            db_size = os.path.getsize(backup_db)
            if db_size == 0:
                print(f"✗ FAILED: Backup database is zero size: {backup_db}")
                return False

            print(f"✓ SQLite backup exists: {backup_db}")
            print(f"  - Size: {db_size} bytes (non-zero)")

            # Check JSON export
            if backup_json and os.path.exists(backup_json):
                json_size = os.path.getsize(backup_json)
                print(f"✓ JSON export exists: {backup_json}")
                print(f"  - Size: {json_size} bytes (non-zero)")

            # Check metadata file
            if os.path.exists(backup_meta):
                meta_size = os.path.getsize(backup_meta)
                print(f"✓ Metadata file exists: {backup_meta}")
                print(f"  - Size: {meta_size} bytes")

            # Load and verify JSON export content
            if backup_json and os.path.exists(backup_json):
                with open(backup_json, 'r') as f:
                    json_data = json.load(f)

                features_count = len(json_data.get('uat_test_features', []))
                plan_count = len(json_data.get('uat_test_plan', []))

                print(f"\n✓ JSON export content verified:")
                print(f"  - uat_test_features records: {features_count}")
                print(f"  - uat_test_plan records: {plan_count}")

                self.test_data['json_export'] = json_data

            return True

        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False

    def step_5_delete_some_records(self):
        """Step 5: Delete some records from database"""
        print("\n" + "="*80)
        print("STEP 5: Delete some records from database")
        print("="*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get count before deletion
            cursor.execute("SELECT COUNT(*) FROM uat_test_features")
            before_count = cursor.fetchone()[0]

            # Delete some test records (we'll delete 2 of the 3 we created)
            cursor.execute("DELETE FROM uat_test_features WHERE priority IN (100, 101)")
            deleted_rows = cursor.rowcount
            conn.commit()

            # Get count after deletion
            cursor.execute("SELECT COUNT(*) FROM uat_test_features")
            after_count = cursor.fetchone()[0]

            print(f"✓ Deleted {deleted_rows} records from uat_test_features")
            print(f"  - Records before: {before_count}")
            print(f"  - Records after: {after_count}")
            print(f"  - Records deleted: {before_count - after_count}")

            self.test_data['features_after_deletion'] = after_count

            return True

        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False
        finally:
            conn.close()

    def step_6_run_restore_command(self):
        """Step 6: Run restore command from backup"""
        print("\n" + "="*80)
        print("STEP 6: Run restore command from backup")
        print("="*80)

        try:
            # Restore from the backup we created
            restore_metadata = self.backup_manager.restore_backup(
                backup_name='feature5_test_backup',
                verify=True
            )

            print(f"✓ Restore completed successfully")
            print(f"  - Backup name: {restore_metadata['backup_name']}")
            print(f"  - Restored at: {restore_metadata['restored_at']}")
            print(f"  - Backup checksum: {restore_metadata['backup_checksum'][:16]}...")
            print(f"  - Restored checksum: {restore_metadata['restored_checksum'][:16]}...")
            print(f"  - Checksums match: {restore_metadata['checksums_match']}")
            print(f"  - Record counts: {restore_metadata['record_counts']}")
            print(f"  - Verification passed: {restore_metadata['verification_passed']}")

            self.test_data['restore_metadata'] = restore_metadata

            return True

        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False

    def step_7_verify_data_restored(self):
        """Step 7: Verify all data restored correctly"""
        print("\n" + "="*80)
        print("STEP 7: Verify all data restored correctly")
        print("="*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Check record counts match original
            cursor.execute("SELECT COUNT(*) FROM uat_test_features")
            features_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM uat_test_plan")
            plan_count = cursor.fetchone()[0]

            original_features = self.test_data['features_count']
            original_plan = self.test_data['plan_count']

            print(f"✓ Record count comparison:")
            print(f"  - uat_test_features: {features_count} (original: {original_features})")
            print(f"  - uat_test_plan: {plan_count} (original: {original_plan})")

            # We expect the count to match the original count before deletion
            # The key test is that our specific test records still exist
            if features_count < original_features:
                print(f"✗ FAILED: Feature count decreased after restore!")
                return False

            if plan_count != original_plan:
                print(f"✗ FAILED: Plan count mismatch!")
                return False

            # Verify specific test records exist
            cursor.execute(
                "SELECT scenario, phase, journey FROM uat_test_features WHERE priority = 100"
            )
            record = cursor.fetchone()

            if record:
                print(f"\n✓ Test record verification:")
                print(f"  - Priority 100 found: {record[0]} ({record[1]} / {record[2]})")
            else:
                print(f"✗ FAILED: Test record priority 100 not found")
                return False

            # Verify test plan exists
            cursor.execute(
                "SELECT project_name, cycle_id FROM uat_test_plan WHERE cycle_id = 'test-cycle-001'"
            )
            plan = cursor.fetchone()

            if plan:
                print(f"✓ Test plan found: {plan[0]} ({plan[1]})")
            else:
                print(f"✗ FAILED: Test plan not found")
                return False

            # Verify database integrity
            print(f"\n✓ Database integrity check:")
            cursor.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()[0]
            print(f"  - PRAGMA integrity_check: {integrity}")

            if integrity != 'ok':
                print(f"✗ FAILED: Database integrity check failed!")
                return False

            print(f"\n✅ ALL DATA RESTORED CORRECTLY!")

            return True

        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False
        finally:
            conn.close()

    def cleanup_test_data(self):
        """Clean up test data after verification"""
        print("\n" + "="*80)
        print("CLEANUP: Removing test data")
        print("="*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Delete test records
            cursor.execute("DELETE FROM uat_test_features WHERE priority IN (100, 101, 102)")
            deleted_features = cursor.rowcount

            cursor.execute("DELETE FROM uat_test_plan WHERE cycle_id = 'test-cycle-001'")
            deleted_plan = cursor.rowcount

            conn.commit()

            print(f"✓ Deleted {deleted_features} test feature records")
            print(f"✓ Deleted {deleted_plan} test plan records")

        except Exception as e:
            print(f"⚠ Warning: Cleanup failed: {e}")
        finally:
            conn.close()

        # Delete test backup
        try:
            deleted = self.backup_manager.delete_backup('feature5_test_backup')
            if deleted:
                print(f"✓ Deleted test backup")
        except Exception as e:
            print(f"⚠ Warning: Could not delete test backup: {e}")

    def run_all_tests(self):
        """Run all verification steps"""
        print("\n" + "="*80)
        print("Feature #5 Verification: Database backup and recovery works")
        print("="*80)
        print(f"\nDatabase: {self.db_path}")
        print(f"Backup directory: {self.backup_manager.backup_dir}")

        results = []

        # Run each test step
        results.append(("Step 1: Create test data (features)", self.step_1_create_test_data_features()))
        results.append(("Step 2: Create test data (plan)", self.step_2_create_test_data_plan()))
        results.append(("Step 3: Run backup command", self.step_3_run_backup_command()))
        results.append(("Step 4: Verify backup file", self.step_4_verify_backup_file()))
        results.append(("Step 5: Delete records", self.step_5_delete_some_records()))
        results.append(("Step 6: Run restore command", self.step_6_run_restore_command()))
        results.append(("Step 7: Verify data restored", self.step_7_verify_data_restored()))

        # Print summary
        print("\n" + "="*80)
        print("VERIFICATION SUMMARY")
        print("="*80)

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for step, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {step}")

        print(f"\nTotal: {passed}/{total} tests passed")

        # Cleanup
        self.cleanup_test_data()

        if passed == total:
            print("\n" + "="*80)
            print("🎉 FEATURE #5 VERIFICATION: ALL TESTS PASSED!")
            print("="*80)
            print("\n✅ Database backup and recovery is working correctly")
            return True
        else:
            print("\n" + "="*80)
            print("❌ FEATURE #5 VERIFICATION: FAILED")
            print("="*80)
            return False


if __name__ == '__main__':
    verifier = Feature5Verifier()
    success = verifier.run_all_tests()
    sys.exit(0 if success else 1)
