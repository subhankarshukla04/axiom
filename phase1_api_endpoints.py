"""
Phase 1 API Endpoints
Scenario Management, Macro Assumptions, and Audit Trail APIs

Add these routes to app.py by importing and registering them
"""

from flask import Blueprint, request, jsonify
from scenario_service import get_scenario_service
from macro_service import get_macro_service
from audit_service import get_audit_service
from scenario_generator import get_scenario_generator
from datetime import datetime
import logging

# Create blueprint
phase1_bp = Blueprint('phase1', __name__)
logger = logging.getLogger(__name__)


# ============================================================================
# SCENARIO MANAGEMENT ENDPOINTS
# ============================================================================

@phase1_bp.route('/api/scenarios/<int:company_id>', methods=['GET'])
def get_scenarios(company_id):
    """Get all scenarios for a company"""
    try:
        service = get_scenario_service()
        scenarios = service.get_scenarios_for_company(company_id)
        return jsonify({
            'success': True,
            'scenarios': scenarios,
            'count': len(scenarios)
        })
    except Exception as e:
        logger.error(f"Error fetching scenarios: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenario/<int:scenario_id>', methods=['GET'])
def get_scenario(scenario_id):
    """Get a specific scenario"""
    try:
        service = get_scenario_service()
        scenario = service.get_scenario_by_id(scenario_id)

        if not scenario:
            return jsonify({'success': False, 'error': 'Scenario not found'}), 404

        return jsonify({
            'success': True,
            'scenario': scenario
        })
    except Exception as e:
        logger.error(f"Error fetching scenario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenarios', methods=['POST'])
def create_scenario():
    """Create a new scenario"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['company_id', 'name', 'description', 'created_by']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        service = get_scenario_service()
        scenario_id = service.create_scenario(
            company_id=data['company_id'],
            name=data['name'],
            description=data['description'],
            created_by=data['created_by'],
            is_default=data.get('is_default', False)
        )

        if not scenario_id:
            return jsonify({'success': False, 'error': 'Failed to create scenario'}), 500

        # If assumptions provided, update them
        if 'assumptions' in data:
            service.update_scenario_assumptions(
                scenario_id,
                data['assumptions'],
                data['created_by']
            )

        return jsonify({
            'success': True,
            'scenario_id': scenario_id,
            'message': 'Scenario created successfully'
        }), 201

    except Exception as e:
        logger.error(f"Error creating scenario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenario/<int:scenario_id>', methods=['PUT'])
def update_scenario(scenario_id):
    """Update scenario assumptions"""
    try:
        data = request.get_json()

        if 'assumptions' not in data or 'changed_by' not in data:
            return jsonify({'success': False, 'error': 'Missing assumptions or changed_by'}), 400

        service = get_scenario_service()
        success = service.update_scenario_assumptions(
            scenario_id,
            data['assumptions'],
            data['changed_by']
        )

        if not success:
            return jsonify({'success': False, 'error': 'Failed to update scenario'}), 500

        return jsonify({
            'success': True,
            'message': 'Scenario updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating scenario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenario/<int:scenario_id>', methods=['DELETE'])
def delete_scenario(scenario_id):
    """Delete a scenario"""
    try:
        service = get_scenario_service()
        success = service.delete_scenario(scenario_id)

        if not success:
            return jsonify({'success': False, 'error': 'Failed to delete scenario'}), 500

        return jsonify({
            'success': True,
            'message': 'Scenario deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting scenario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenario/<int:scenario_id>/clone', methods=['POST'])
def clone_scenario(scenario_id):
    """Clone a scenario"""
    try:
        data = request.get_json()

        required_fields = ['new_name', 'new_description', 'created_by']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        service = get_scenario_service()
        new_scenario_id = service.clone_scenario(
            scenario_id,
            data['new_name'],
            data['new_description'],
            data['created_by']
        )

        if not new_scenario_id:
            return jsonify({'success': False, 'error': 'Failed to clone scenario'}), 500

        return jsonify({
            'success': True,
            'scenario_id': new_scenario_id,
            'message': 'Scenario cloned successfully'
        }), 201

    except Exception as e:
        logger.error(f"Error cloning scenario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenario/<int:scenario_id>/set-default', methods=['POST'])
def set_default_scenario(scenario_id):
    """Set a scenario as default"""
    try:
        data = request.get_json()

        if 'company_id' not in data:
            return jsonify({'success': False, 'error': 'Missing company_id'}), 400

        service = get_scenario_service()
        success = service.set_default_scenario(data['company_id'], scenario_id)

        if not success:
            return jsonify({'success': False, 'error': 'Failed to set default scenario'}), 500

        return jsonify({
            'success': True,
            'message': 'Default scenario updated'
        })

    except Exception as e:
        logger.error(f"Error setting default scenario: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenario/compare', methods=['GET'])
def compare_scenarios():
    """Compare multiple scenarios"""
    try:
        company_id = request.args.get('company_id', type=int)
        scenario_ids_str = request.args.get('scenario_ids', '')

        if not company_id or not scenario_ids_str:
            return jsonify({'success': False, 'error': 'Missing company_id or scenario_ids'}), 400

        # Parse scenario IDs
        scenario_ids = [int(id.strip()) for id in scenario_ids_str.split(',')]

        service = get_scenario_service()
        comparison = service.compare_scenarios(company_id, scenario_ids)

        if not comparison:
            return jsonify({'success': False, 'error': 'Failed to compare scenarios'}), 500

        return jsonify({
            'success': True,
            'comparison': comparison
        })

    except Exception as e:
        logger.error(f"Error comparing scenarios: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/scenario/generate-defaults', methods=['POST'])
def generate_default_scenarios():
    """Auto-generate Bear/Base/Bull scenarios"""
    try:
        data = request.get_json()

        required_fields = ['company_id', 'created_by']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        generator = get_scenario_generator()
        scenario_ids = generator.generate_default_scenarios(
            data['company_id'],
            data['created_by']
        )

        if not scenario_ids:
            return jsonify({'success': False, 'error': 'Failed to generate scenarios'}), 500

        return jsonify({
            'success': True,
            'scenario_ids': scenario_ids,
            'count': len(scenario_ids),
            'message': 'Default scenarios generated'
        }), 201

    except Exception as e:
        logger.error(f"Error generating scenarios: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# MACRO ASSUMPTIONS ENDPOINTS
# ============================================================================

@phase1_bp.route('/api/macro-environments', methods=['GET'])
def get_macro_environments():
    """Get all macro environments"""
    try:
        service = get_macro_service()
        environments = service.get_all_macro_environments()

        return jsonify({
            'success': True,
            'environments': environments,
            'count': len(environments)
        })

    except Exception as e:
        logger.error(f"Error fetching macro environments: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/macro-environment/<int:macro_id>', methods=['GET'])
def get_macro_environment(macro_id):
    """Get a specific macro environment"""
    try:
        service = get_macro_service()
        environment = service.get_macro_environment_by_id(macro_id)

        if not environment:
            return jsonify({'success': False, 'error': 'Macro environment not found'}), 404

        return jsonify({
            'success': True,
            'environment': environment
        })

    except Exception as e:
        logger.error(f"Error fetching macro environment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/macro-environment/active', methods=['GET'])
def get_active_macro_environment():
    """Get the active macro environment"""
    try:
        service = get_macro_service()
        environment = service.get_active_macro_environment()

        if not environment:
            return jsonify({'success': False, 'error': 'No active macro environment'}), 404

        return jsonify({
            'success': True,
            'environment': environment
        })

    except Exception as e:
        logger.error(f"Error fetching active macro environment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/macro-environment', methods=['POST'])
def create_macro_environment():
    """Create a new macro environment"""
    try:
        data = request.get_json()

        required_fields = ['name', 'description', 'assumptions', 'created_by']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        service = get_macro_service()
        macro_id = service.create_macro_environment(
            data['name'],
            data['description'],
            data['assumptions'],
            data['created_by']
        )

        if not macro_id:
            return jsonify({'success': False, 'error': 'Failed to create macro environment'}), 500

        return jsonify({
            'success': True,
            'macro_id': macro_id,
            'message': 'Macro environment created'
        }), 201

    except Exception as e:
        logger.error(f"Error creating macro environment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/macro-environment/<int:macro_id>', methods=['PUT'])
def update_macro_environment(macro_id):
    """Update macro environment assumptions"""
    try:
        data = request.get_json()

        if 'assumptions' not in data or 'changed_by' not in data:
            return jsonify({'success': False, 'error': 'Missing assumptions or changed_by'}), 400

        service = get_macro_service()
        success = service.update_macro_assumptions(
            macro_id,
            data['assumptions'],
            data['changed_by']
        )

        if not success:
            return jsonify({'success': False, 'error': 'Failed to update macro environment'}), 500

        return jsonify({
            'success': True,
            'message': 'Macro environment updated'
        })

    except Exception as e:
        logger.error(f"Error updating macro environment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/macro-environment/<int:macro_id>/activate', methods=['POST'])
def activate_macro_environment(macro_id):
    """Activate a macro environment"""
    try:
        service = get_macro_service()
        success = service.activate_macro_environment(macro_id)

        if not success:
            return jsonify({'success': False, 'error': 'Failed to activate macro environment'}), 500

        return jsonify({
            'success': True,
            'message': 'Macro environment activated'
        })

    except Exception as e:
        logger.error(f"Error activating macro environment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/macro-environment/<int:macro_id>/apply-to-portfolio', methods=['POST'])
def apply_macro_to_portfolio(macro_id):
    """Apply macro environment to entire portfolio"""
    try:
        service = get_macro_service()
        updated_companies = service.apply_macro_to_portfolio(macro_id)

        return jsonify({
            'success': True,
            'updated_companies': updated_companies,
            'count': len(updated_companies),
            'message': f'Macro environment applied to {len(updated_companies)} companies'
        })

    except Exception as e:
        logger.error(f"Error applying macro to portfolio: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/sector-multiples/<string:sector>', methods=['GET'])
def get_sector_multiples(sector):
    """Get sector multiples for active macro environment"""
    try:
        macro_id = request.args.get('macro_id', type=int)

        service = get_macro_service()
        multiples = service.get_sector_multiples(sector, macro_id)

        if not multiples:
            return jsonify({'success': False, 'error': 'Sector multiples not found'}), 404

        return jsonify({
            'success': True,
            'multiples': multiples
        })

    except Exception as e:
        logger.error(f"Error fetching sector multiples: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/sector-multiples', methods=['GET'])
def get_all_sector_multiples():
    """Get all sector multiples for a macro environment"""
    try:
        macro_id = request.args.get('macro_id', type=int)

        service = get_macro_service()
        multiples = service.get_all_sector_multiples(macro_id)

        return jsonify({
            'success': True,
            'multiples': multiples,
            'count': len(multiples)
        })

    except Exception as e:
        logger.error(f"Error fetching sector multiples: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# AUDIT TRAIL ENDPOINTS
# ============================================================================

@phase1_bp.route('/api/audit-trail', methods=['GET'])
def get_audit_trail():
    """Get audit trail with filters"""
    try:
        # Parse query parameters
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id', type=int)
        changed_by = request.args.get('changed_by', type=int)
        is_material = request.args.get('is_material', type=bool)
        limit = request.args.get('limit', default=100, type=int)
        offset = request.args.get('offset', default=0, type=int)

        # Parse dates
        start_date = None
        end_date = None

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))

        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        service = get_audit_service()
        entries = service.get_audit_trail(
            entity_type=entity_type,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
            changed_by=changed_by,
            is_material_only=is_material,
            limit=limit,
            offset=offset
        )

        return jsonify({
            'success': True,
            'entries': entries,
            'count': len(entries)
        })

    except Exception as e:
        logger.error(f"Error fetching audit trail: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/audit-trail/material', methods=['GET'])
def get_material_changes():
    """Get material changes"""
    try:
        # Parse dates
        start_date = None
        end_date = None

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))

        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        service = get_audit_service()
        changes = service.get_material_changes(start_date, end_date)

        return jsonify({
            'success': True,
            'changes': changes,
            'count': len(changes)
        })

    except Exception as e:
        logger.error(f"Error fetching material changes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/audit-trail/user/<int:user_id>', methods=['GET'])
def get_user_changes(user_id):
    """Get all changes by a user"""
    try:
        # Parse dates
        start_date = None
        end_date = None
        limit = request.args.get('limit', default=100, type=int)

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))

        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        service = get_audit_service()
        changes = service.get_user_changes(user_id, start_date, end_date, limit)

        return jsonify({
            'success': True,
            'changes': changes,
            'count': len(changes)
        })

    except Exception as e:
        logger.error(f"Error fetching user changes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/audit-trail/export', methods=['GET'])
def export_audit_log():
    """Export audit log to CSV"""
    try:
        # Parse filters
        entity_type = request.args.get('entity_type')
        changed_by = request.args.get('changed_by', type=int)

        start_date = None
        end_date = None

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))

        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        service = get_audit_service()
        csv_data = service.export_audit_log(entity_type, start_date, end_date, changed_by)

        from flask import Response
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=audit_log.csv'}
        )

    except Exception as e:
        logger.error(f"Error exporting audit log: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@phase1_bp.route('/api/audit-trail/rollback', methods=['POST'])
def rollback_assumptions():
    """Rollback entity to previous state"""
    try:
        data = request.get_json()

        required_fields = ['entity_type', 'entity_id', 'rollback_date', 'executed_by']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

        rollback_date = datetime.fromisoformat(data['rollback_date'])

        service = get_audit_service()
        success = service.rollback_to_date(
            data['entity_type'],
            data['entity_id'],
            rollback_date,
            data['executed_by']
        )

        if not success:
            return jsonify({'success': False, 'error': 'Failed to rollback'}), 500

        return jsonify({
            'success': True,
            'message': f'Rolled back to {rollback_date}'
        })

    except Exception as e:
        logger.error(f"Error rolling back: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HELPER FUNCTION TO REGISTER BLUEPRINT
# ============================================================================

def register_phase1_routes(app):
    """
    Register Phase 1 routes with Flask app

    Usage in app.py:
        from phase1_api_endpoints import register_phase1_routes
        register_phase1_routes(app)
    """
    app.register_blueprint(phase1_bp)
    logger.info("Phase 1 API endpoints registered")
