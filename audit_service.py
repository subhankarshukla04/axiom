"""
Audit Trail Service
Tracks all assumption changes with full history and rollback capability
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import csv
import io

logger = logging.getLogger(__name__)


class AuditService:
    """Service for tracking and managing assumption changes"""

    def __init__(self, db_connection_string: str = None):
        self.db_connection_string = db_connection_string or Config.get_db_connection_string()

    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(
            self.db_connection_string,
            cursor_factory=RealDictCursor
        )

    def log_assumption_change(
        self,
        entity_type: str,
        entity_id: int,
        field_name: str,
        old_value: str,
        new_value: str,
        changed_by: int,
        user_role: str,
        change_reason: str = None,
        change_type: str = 'manual_edit',
        ip_address: str = None,
        user_agent: str = None
    ) -> Optional[int]:
        """
        Log an assumption change to the audit trail

        Args:
            entity_type: Type of entity ('company_financials', 'scenario_assumptions', etc.)
            entity_id: ID of the entity
            field_name: Name of the field that changed
            old_value: Previous value (as string)
            new_value: New value (as string)
            changed_by: User ID who made the change
            user_role: Role of the user
            change_reason: Optional reason for the change
            change_type: Type of change ('manual_edit', 'scenario_switch', 'macro_update', etc.)
            ip_address: IP address of the user
            user_agent: User agent string

        Returns:
            Audit log ID if successful, None otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Determine if change is material (>10% change for numeric fields)
            is_material = self._is_material_change(field_name, old_value, new_value)

            cursor.execute("""
                INSERT INTO assumption_audit_log (
                    entity_type, entity_id, field_name, old_value, new_value,
                    changed_by, user_role, change_reason, change_type,
                    ip_address, user_agent, is_material
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                entity_type, entity_id, field_name, str(old_value), str(new_value),
                changed_by, user_role, change_reason, change_type,
                ip_address, user_agent, is_material
            ))

            audit_id = cursor.fetchone()['id']
            conn.commit()

            logger.info(f"Logged audit entry {audit_id} for {entity_type}:{entity_id}.{field_name}")
            return audit_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Error logging assumption change: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def _is_material_change(self, field_name: str, old_value: str, new_value: str) -> bool:
        """
        Determine if a change is material (>10% for numeric fields)

        Args:
            field_name: Field name
            old_value: Old value
            new_value: New value

        Returns:
            True if material change, False otherwise
        """
        try:
            # List of numeric fields that should be checked for materiality
            numeric_fields = [
                'growth_rate_y1', 'growth_rate_y2', 'growth_rate_y3', 'terminal_growth',
                'wacc', 'beta', 'risk_free_rate', 'market_risk_premium',
                'profit_margin', 'ebitda_margin', 'tax_rate', 'capex_pct',
                'comparable_ev_ebitda', 'comparable_pe'
            ]

            if field_name not in numeric_fields:
                return False

            old_float = float(old_value)
            new_float = float(new_value)

            # Avoid division by zero
            if old_float == 0:
                return new_float != 0

            # Calculate percentage change
            pct_change = abs((new_float - old_float) / old_float)

            # Material if >10% change
            return pct_change > 0.10

        except (ValueError, TypeError):
            return False

    def get_audit_trail(
        self,
        entity_type: str = None,
        entity_id: int = None,
        start_date: datetime = None,
        end_date: datetime = None,
        changed_by: int = None,
        is_material_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get audit trail entries with optional filters

        Args:
            entity_type: Filter by entity type
            entity_id: Filter by entity ID
            start_date: Filter by start date
            end_date: Filter by end date
            changed_by: Filter by user ID
            is_material_only: Only show material changes
            limit: Maximum number of entries to return
            offset: Offset for pagination

        Returns:
            List of audit entry dictionaries
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Build query with filters
            where_clauses = []
            params = []

            if entity_type:
                where_clauses.append("entity_type = %s")
                params.append(entity_type)

            if entity_id:
                where_clauses.append("entity_id = %s")
                params.append(entity_id)

            if start_date:
                where_clauses.append("changed_at >= %s")
                params.append(start_date)

            if end_date:
                where_clauses.append("changed_at <= %s")
                params.append(end_date)

            if changed_by:
                where_clauses.append("changed_by = %s")
                params.append(changed_by)

            if is_material_only:
                where_clauses.append("is_material = TRUE")

            where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            params.extend([limit, offset])

            query = f"""
                SELECT
                    id, entity_type, entity_id, field_name, old_value, new_value,
                    changed_by, user_role, changed_at, change_reason, change_type,
                    ip_address, is_material
                FROM assumption_audit_log
                {where_clause}
                ORDER BY changed_at DESC
                LIMIT %s OFFSET %s
            """

            cursor.execute(query, params)

            entries = cursor.fetchall()
            return [dict(entry) for entry in entries]

        except Exception as e:
            logger.error(f"Error fetching audit trail: {e}")
            return []

        finally:
            cursor.close()
            conn.close()

    def get_material_changes(
        self,
        start_date: datetime = None,
        end_date: datetime = None,
        threshold: float = 0.10
    ) -> List[Dict]:
        """
        Get all material changes within a date range

        Args:
            start_date: Start date filter
            end_date: End date filter
            threshold: Threshold for materiality (default 10%)

        Returns:
            List of material change dictionaries
        """
        return self.get_audit_trail(
            start_date=start_date,
            end_date=end_date,
            is_material_only=True
        )

    def get_user_changes(
        self,
        user_id: int,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get all changes made by a specific user

        Args:
            user_id: User ID
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum number of entries

        Returns:
            List of change dictionaries
        """
        return self.get_audit_trail(
            changed_by=user_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

    def get_entity_history(
        self,
        entity_type: str,
        entity_id: int
    ) -> List[Dict]:
        """
        Get full change history for a specific entity

        Args:
            entity_type: Entity type
            entity_id: Entity ID

        Returns:
            List of changes in chronological order
        """
        return self.get_audit_trail(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=1000
        )

    def get_change_summary(self, company_id: int) -> Dict:
        """
        Get summary of changes for a company

        Args:
            company_id: Company ID

        Returns:
            Summary dictionary with statistics
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get total changes
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM assumption_audit_log
                WHERE entity_type = 'company_financials' AND entity_id = %s
            """, (company_id,))
            total_changes = cursor.fetchone()['count']

            # Get material changes
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM assumption_audit_log
                WHERE entity_type = 'company_financials' AND entity_id = %s AND is_material = TRUE
            """, (company_id,))
            material_changes = cursor.fetchone()['count']

            # Get last change date
            cursor.execute("""
                SELECT MAX(changed_at) as last_change
                FROM assumption_audit_log
                WHERE entity_type = 'company_financials' AND entity_id = %s
            """, (company_id,))
            last_change = cursor.fetchone()['last_change']

            # Get unique users who made changes
            cursor.execute("""
                SELECT COUNT(DISTINCT changed_by) as count
                FROM assumption_audit_log
                WHERE entity_type = 'company_financials' AND entity_id = %s
            """, (company_id,))
            unique_users = cursor.fetchone()['count']

            return {
                'total_changes': total_changes,
                'material_changes': material_changes,
                'last_change': last_change,
                'unique_users': unique_users
            }

        except Exception as e:
            logger.error(f"Error getting change summary: {e}")
            return {}

        finally:
            cursor.close()
            conn.close()

    def rollback_to_date(
        self,
        entity_type: str,
        entity_id: int,
        rollback_date: datetime,
        executed_by: int
    ) -> bool:
        """
        Rollback entity to state at a specific date

        Args:
            entity_type: Entity type
            entity_id: Entity ID
            rollback_date: Date to rollback to
            executed_by: User ID executing the rollback

        Returns:
            True if successful, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get all changes after the rollback date
            cursor.execute("""
                SELECT field_name, old_value
                FROM assumption_audit_log
                WHERE entity_type = %s AND entity_id = %s AND changed_at > %s
                ORDER BY changed_at ASC
            """, (entity_type, entity_id, rollback_date))

            changes = cursor.fetchall()

            if not changes:
                logger.info(f"No changes to rollback for {entity_type}:{entity_id}")
                return True

            # Determine target table
            if entity_type == 'company_financials':
                table = 'company_financials'
                id_field = 'company_id'
            elif entity_type == 'scenario_assumptions':
                table = 'scenario_assumptions'
                id_field = 'scenario_id'
            elif entity_type == 'macro_assumptions':
                table = 'macro_assumptions'
                id_field = 'id'
            else:
                logger.error(f"Unknown entity type: {entity_type}")
                return False

            # Apply rollback (restore old values)
            for change in changes:
                field = change['field_name']
                old_value = change['old_value']

                # Update the field to its old value
                cursor.execute(f"""
                    UPDATE {table}
                    SET {field} = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE {id_field} = %s
                """, (old_value, entity_id))

                # Log the rollback action
                self.log_assumption_change(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_name=field,
                    old_value=change['new_value'],  # Current value
                    new_value=old_value,  # Rolled back value
                    changed_by=executed_by,
                    user_role='admin',
                    change_reason=f'Rollback to {rollback_date}',
                    change_type='rollback'
                )

            conn.commit()
            logger.info(f"Rolled back {entity_type}:{entity_id} to {rollback_date}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error rolling back: {e}")
            return False

        finally:
            cursor.close()
            conn.close()

    def export_audit_log(
        self,
        entity_type: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        changed_by: int = None
    ) -> str:
        """
        Export audit log to CSV format

        Args:
            entity_type: Filter by entity type
            start_date: Filter by start date
            end_date: Filter by end date
            changed_by: Filter by user ID

        Returns:
            CSV string
        """
        entries = self.get_audit_trail(
            entity_type=entity_type,
            start_date=start_date,
            end_date=end_date,
            changed_by=changed_by,
            limit=10000
        )

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'ID', 'Entity Type', 'Entity ID', 'Field Name', 'Old Value', 'New Value',
            'Changed By', 'User Role', 'Changed At', 'Change Reason', 'Change Type',
            'Is Material', 'IP Address'
        ])

        # Write rows
        for entry in entries:
            writer.writerow([
                entry['id'],
                entry['entity_type'],
                entry['entity_id'],
                entry['field_name'],
                entry['old_value'],
                entry['new_value'],
                entry['changed_by'],
                entry['user_role'],
                entry['changed_at'],
                entry['change_reason'] or '',
                entry['change_type'],
                entry['is_material'],
                entry['ip_address'] or ''
            ])

        return output.getvalue()


# Convenience function
def get_audit_service() -> AuditService:
    """Get instance of AuditService"""
    return AuditService()
