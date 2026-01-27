"""
Journey Visualizer - Generate flow diagrams for user journeys

This module provides functionality to visualize user journeys as flow diagrams,
showing the flow between scenarios and steps in a clear, structured format.

Feature #162: Journey visualizer shows flow diagram
Feature #164: Journey visualizer shows dependency visualization
Feature #166: Journey visualizer supports zoom and pan
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import AdapterError, handle_errors

# Import journey data models
from uat_gateway.journey_extractor.journey_extractor import Journey, Scenario, JourneyStep, ScenarioType


# ============================================================================
# Data Models
# ============================================================================

class DiagramFormat(str, Enum):
    """Supported diagram formats"""
    ASCII = "ascii"  # Text-based ASCII art
    MERMAID = "mermaid"  # Mermaid.js format
    DOT = "dot"  # Graphviz DOT format
    JSON = "json"  # Structured JSON representation


@dataclass
class FlowNode:
    """Represents a node in the flow diagram"""
    node_id: str
    label: str
    node_type: str  # 'journey', 'scenario', 'step', 'start', 'end'
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.node_id,
            "label": self.label,
            "type": self.node_type,
            "description": self.description,
            "metadata": self.metadata
        }


@dataclass
class FlowArrow:
    """Represents an arrow/connection between nodes"""
    from_node: str
    to_node: str
    label: Optional[str] = None
    arrow_type: str = "solid"  # solid, dashed, dotted

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "from": self.from_node,
            "to": self.to_node,
            "label": self.label,
            "type": self.arrow_type
        }


@dataclass
class FlowDiagram:
    """Complete flow diagram with nodes and arrows"""
    journey_name: str
    nodes: List[FlowNode] = field(default_factory=list)
    arrows: List[FlowArrow] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Add zoom/pan metadata for interactive viewing
    zoom_pan_enabled: bool = True

    def add_node(self, node: FlowNode) -> None:
        """Add a node to the diagram"""
        self.nodes.append(node)

    def add_arrow(self, arrow: FlowArrow) -> None:
        """Add an arrow to the diagram"""
        self.arrows.append(arrow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "journey_name": self.journey_name,
            "nodes": [node.to_dict() for node in self.nodes],
            "arrows": [arrow.to_dict() for arrow in self.arrows],
            "metadata": self.metadata,
            "zoom_pan_enabled": self.zoom_pan_enabled
        }


# ============================================================================
# Dependency Visualization Data Models (Feature #164)
# ============================================================================

class DependencyLevel(str, Enum):
    """Dependency impact levels for visualization"""
    CRITICAL = "critical"  # On critical path, blocks multiple scenarios
    HIGH = "high"  # Blocks several scenarios
    MEDIUM = "medium"  # Blocks one or few scenarios
    LOW = "low"  # Optional dependency, minimal impact


@dataclass
class ScenarioNode:
    """Represents a scenario node in the dependency graph"""
    scenario_id: str
    name: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)  # Scenarios that depend on this one
    is_on_critical_path: bool = False

    def __str__(self) -> str:
        critical_marker = " ⚡" if self.is_on_critical_path else ""
        deps = f" [{len(self.depends_on)} deps]" if self.depends_on else ""
        return f"Node({self.name}{deps}{critical_marker})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "depends_on": self.depends_on,
            "dependents": self.dependents,
            "is_on_critical_path": self.is_on_critical_path
        }


@dataclass
class DependencyEdge:
    """Represents a directed dependency edge between scenarios"""
    from_scenario_id: str
    to_scenario_id: str
    level: DependencyLevel = DependencyLevel.MEDIUM

    def __str__(self) -> str:
        arrow = "→" if self.level == DependencyLevel.MEDIUM else "⇒" if self.level == DependencyLevel.HIGH else "➔"
        return f"{self.from_scenario_id} {arrow} {self.to_scenario_id}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "from": self.from_scenario_id,
            "to": self.to_scenario_id,
            "level": self.level.value
        }


@dataclass
class DependencyGraph:
    """Represents the complete dependency graph for a journey"""
    journey_id: str
    journey_name: str
    nodes: Dict[str, ScenarioNode] = field(default_factory=dict)
    edges: List[DependencyEdge] = field(default_factory=list)
    critical_path: List[str] = field(default_factory=list)

    def get_node(self, scenario_id: str) -> Optional[ScenarioNode]:
        """Get a node by scenario ID"""
        return self.nodes.get(scenario_id)

    def get_dependencies_for(self, scenario_id: str) -> List[str]:
        """Get list of scenario IDs that this scenario depends on"""
        node = self.get_node(scenario_id)
        return node.depends_on if node else []

    def get_dependents_for(self, scenario_id: str) -> List[str]:
        """Get list of scenario IDs that depend on this scenario"""
        node = self.get_node(scenario_id)
        return node.dependents if node else []

    def is_on_critical_path(self, scenario_id: str) -> bool:
        """Check if a scenario is on the critical path"""
        node = self.get_node(scenario_id)
        return node.is_on_critical_path if node else False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "journey_id": self.journey_id,
            "journey_name": self.journey_name,
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
            "critical_path": self.critical_path
        }


# ============================================================================
# Zoom and Pan State Models (Feature #166)
# ============================================================================

@dataclass
class ZoomPanState:
    """Current zoom and pan state for a diagram"""
    zoom_level: float = 1.0  # 1.0 = 100%, 2.0 = 200%, 0.5 = 50%
    pan_x: float = 0.0  # Horizontal pan offset in pixels
    pan_y: float = 0.0  # Vertical pan offset in pixels
    min_zoom: float = 0.25  # Minimum zoom level (25%)
    max_zoom: float = 4.0  # Maximum zoom level (400%)

    def can_zoom_in(self) -> bool:
        """Check if can zoom in further"""
        return self.zoom_level < self.max_zoom

    def can_zoom_out(self) -> bool:
        """Check if can zoom out further"""
        return self.zoom_level > self.min_zoom

    def zoom_in(self, step: float = 1.2) -> 'ZoomPanState':
        """Zoom in by a step factor"""
        new_zoom = min(self.zoom_level * step, self.max_zoom)
        return ZoomPanState(
            zoom_level=new_zoom,
            pan_x=self.pan_x,
            pan_y=self.pan_y,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom
        )

    def zoom_out(self, step: float = 1.2) -> 'ZoomPanState':
        """Zoom out by a step factor"""
        new_zoom = max(self.zoom_level / step, self.min_zoom)
        return ZoomPanState(
            zoom_level=new_zoom,
            pan_x=self.pan_x,
            pan_y=self.pan_y,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom
        )

    def pan(self, dx: float, dy: float) -> 'ZoomPanState':
        """Pan by offset amounts"""
        return ZoomPanState(
            zoom_level=self.zoom_level,
            pan_x=self.pan_x + dx,
            pan_y=self.pan_y + dy,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom
        )

    def reset(self) -> 'ZoomPanState':
        """Reset to default state"""
        return ZoomPanState(
            zoom_level=1.0,
            pan_x=0.0,
            pan_y=0.0,
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "zoom_level": round(self.zoom_level, 2),
            "pan_x": round(self.pan_x, 2),
            "pan_y": round(self.pan_y, 2),
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom
        }


# ============================================================================
# Journey Visualizer Implementation
# ============================================================================

class JourneyVisualizer:
    """
    Generate flow diagrams for user journeys

    This visualizer creates clear, structured flow diagrams showing:
    - Journey as the starting point
    - Scenarios as branches
    - Steps within each scenario
    - Flow arrows showing the sequence

    Supported output formats:
    - ASCII: Text-based art for terminal display
    - Mermaid: Mermaid.js syntax for web rendering
    - DOT: Graphviz format for advanced visualization
    - JSON: Structured data for programmatic use
    """

    def __init__(
        self,
        default_format: DiagramFormat = DiagramFormat.ASCII,
        show_steps: bool = True,
        show_descriptions: bool = True
    ):
        """
        Initialize the journey visualizer

        Args:
            default_format: Default diagram format to generate
            show_steps: Whether to show individual steps in scenarios
            show_descriptions: Whether to include descriptions in nodes
        """
        self.logger = get_logger(__name__)
        self.default_format = default_format
        self.show_steps = show_steps
        self.show_descriptions = show_descriptions

        self.logger.info(
            f"JourneyVisualizer initialized: format={default_format}, "
            f"show_steps={show_steps}, show_descriptions={show_descriptions}"
        )

    @handle_errors(component="journey_visualizer", reraise=True)
    def generate_flow_diagram(
        self,
        journey: Journey,
        output_format: Optional[DiagramFormat] = None
    ) -> FlowDiagram:
        """
        Generate a flow diagram for a journey

        This method creates a structured representation of the journey flow,
        including scenarios and steps as nodes, with arrows showing connections.

        Args:
            journey: Journey to visualize
            output_format: Format to generate (uses default if not specified)

        Returns:
            FlowDiagram with nodes and arrows representing the journey flow
        """
        format_type = output_format or self.default_format

        self.logger.info(
            f"Generating flow diagram for journey: {journey.name} "
            f"(format={format_type}, scenarios={len(journey.scenarios)})"
        )

        # Create flow diagram
        diagram = FlowDiagram(
            journey_name=journey.name,
            metadata={
                "journey_id": journey.journey_id,
                "journey_type": journey.journey_type.value,
                "priority": journey.priority,
                "format": format_type.value,
                "scenario_count": len(journey.scenarios)
            }
        )

        # Add journey start node
        start_node = FlowNode(
            node_id=f"{journey.journey_id}_start",
            label=f"🚀 {journey.name}",
            node_type="start",
            description=journey.description,
            metadata={"journey_type": journey.journey_type.value}
        )
        diagram.add_node(start_node)

        # Process each scenario
        for idx, scenario in enumerate(journey.scenarios):
            # Create scenario node
            scenario_icon = self._get_scenario_icon(scenario.scenario_type)
            scenario_node = FlowNode(
                node_id=scenario.scenario_id,
                label=f"{scenario_icon} {scenario.name}",
                node_type="scenario",
                description=scenario.description if self.show_descriptions else None,
                metadata={
                    "scenario_type": scenario.scenario_type.value,
                    "step_count": len(scenario.steps),
                    "index": idx
                }
            )
            diagram.add_node(scenario_node)

            # Add arrow from journey start to scenario
            diagram.add_arrow(FlowArrow(
                from_node=start_node.node_id,
                to_node=scenario.scenario_id,
                label=f"Scenario {idx + 1}"
            ))

            # Add steps if enabled
            if self.show_steps:
                self._add_step_nodes(diagram, scenario, scenario_node.node_id)

        # Add end node
        end_node = FlowNode(
            node_id=f"{journey.journey_id}_end",
            label="✓ Complete",
            node_type="end"
        )
        diagram.add_node(end_node)

        # Connect all scenarios to end
        for scenario in journey.scenarios:
            diagram.add_arrow(FlowArrow(
                from_node=scenario.scenario_id,
                to_node=end_node.node_id,
                arrow_type="dashed"
            ))

        self.logger.info(
            f"Flow diagram generated: {len(diagram.nodes)} nodes, "
            f"{len(diagram.arrows)} arrows"
        )

        return diagram

    def _add_step_nodes(
        self,
        diagram: FlowDiagram,
        scenario: Scenario,
        parent_node_id: str
    ) -> None:
        """
        Add step nodes to the diagram

        Args:
            diagram: Flow diagram to add nodes to
            scenario: Scenario containing steps
            parent_node_id: ID of the parent scenario node
        """
        for step_idx, step in enumerate(scenario.steps):
            # Create step node
            step_icon = self._get_step_icon(step.action_type)
            step_node = FlowNode(
                node_id=f"{scenario.scenario_id}_step_{step_idx}",
                label=f"{step_icon} {step.action_type}",
                node_type="step",
                description=step.description if self.show_descriptions else None,
                metadata={
                    "target": step.target,
                    "expected_result": step.expected_result,
                    "step_index": step_idx
                }
            )
            diagram.add_node(step_node)

            # Connect step to previous node
            if step_idx == 0:
                # First step connects to scenario
                from_node = parent_node_id
            else:
                # Subsequent steps connect to previous step
                from_node = f"{scenario.scenario_id}_step_{step_idx - 1}"

            diagram.add_arrow(FlowArrow(
                from_node=from_node,
                to_node=step_node.node_id
            ))

    def _get_scenario_icon(self, scenario_type: ScenarioType) -> str:
        """Get icon for scenario type"""
        icons = {
            ScenarioType.HAPPY_PATH: "😊",
            ScenarioType.ERROR_PATH: "⚠️"
        }
        return icons.get(scenario_type, "📋")

    def _get_step_icon(self, action_type: str) -> str:
        """Get icon for action type"""
        icons = {
            "navigate": "🌐",
            "click": "👆",
            "type": "⌨️",
            "wait": "⏳",
            "assert": "✓",
            "fill": "📝",
            "select": "🔽",
            "hover": "🖱️",
            "scroll": "📜"
        }
        return icons.get(action_type.lower(), "•")

    @handle_errors(component="journey_visualizer")
    def render_ascii(self, diagram: FlowDiagram) -> str:
        """
        Render flow diagram as ASCII art

        Creates a text-based representation suitable for terminal display.

        Args:
            diagram: Flow diagram to render

        Returns:
            ASCII art string representation
        """
        lines = []
        lines.append("=" * 60)
        lines.append(f"📊 Journey Flow: {diagram.journey_name}")
        lines.append("=" * 60)
        lines.append("")

        # Group nodes by type
        start_nodes = [n for n in diagram.nodes if n.node_type == "start"]
        scenario_nodes = [n for n in diagram.nodes if n.node_type == "scenario"]
        step_nodes = [n for n in diagram.nodes if n.node_type == "step"]
        end_nodes = [n for n in diagram.nodes if n.node_type == "end"]

        # Render start node
        for node in start_nodes:
            lines.append(f"┌─ {node.label} ─┐")
            if node.description:
                lines.append(f"│ {node.description}")
            lines.append("└─────────────┘")
            lines.append("      │")
            lines.append("      ▼")

        # Render scenarios
        for idx, scenario_node in enumerate(scenario_nodes):
            is_last = idx == len(scenario_nodes) - 1

            # Scenario box
            connector = "└───" if is_last else "├───"
            lines.append(f"{connector} {scenario_node.label}")
            if scenario_node.description:
                lines.append(f"│   {scenario_node.description}")

            # Find and render steps for this scenario
            scenario_steps = [
                n for n in step_nodes
                if n.node_id.startswith(scenario_node.node_id + "_step")
            ]

            if scenario_steps:
                for step_idx, step_node in enumerate(scenario_steps):
                    is_last_step = step_idx == len(scenario_steps) - 1
                    step_connector = "    └───" if is_last_step else "    ├───"
                    lines.append(f"{step_connector} {step_node.label}")
                    if step_node.description:
                        lines.append(f"│       {step_node.description}")

            # Show connection to next scenario or end
            if not is_last:
                lines.append("│")
            else:
                lines.append("    │")

        # Render end node
        for node in end_nodes:
            lines.append("    ▼")
            lines.append(f"┌─ {node.label} ─┐")
            lines.append("└─────────────┘")

        lines.append("")
        lines.append(f"Nodes: {len(diagram.nodes)} | Arrows: {len(diagram.arrows)}")

        return "\n".join(lines)

    @handle_errors(component="journey_visualizer")
    def render_mermaid(self, diagram: FlowDiagram) -> str:
        """
        Render flow diagram as Mermaid.js syntax

        Generates Mermaid graph definition that can be rendered in web browsers.

        Args:
            diagram: Flow diagram to render

        Returns:
            Mermaid.js syntax string
        """
        lines = []
        lines.append("graph TD")

        # Define nodes
        for node in diagram.nodes:
            # Escape special characters in labels
            label = node.label.replace('"', '\\"')
            if node.description and self.show_descriptions:
                label = f"{label}\\n{node.description}"

            # Use different shapes based on node type
            if node.node_type == "start":
                shape_id = f"{node.node_id}([/{label}/])"
            elif node.node_type == "end":
                shape_id = f"{node.node_id}([[{label}]])"
            elif node.node_type == "scenario":
                shape_id = f"{node.node_id}[{label}]"
            else:
                shape_id = f"{node.node_id}[{label}]"

            lines.append(f"  {shape_id}")

        # Define arrows
        for arrow in diagram.arrows:
            if arrow.label:
                lines.append(f"  {arrow.from_node} -->|{arrow.label}| {arrow.to_node}")
            else:
                lines.append(f"  {arrow.from_node} --> {arrow.to_node}")

        # Add styling
        lines.append("")
        lines.append("  classDef startStyle fill:#90EE90,stroke:#4CAF50,stroke-width:3px")
        lines.append("  classDef endStyle fill:#87CEEB,stroke:#2196F3,stroke-width:3px")
        lines.append("  classDef scenarioStyle fill:#FFFACD,stroke:#FFC107,stroke-width:2px")
        lines.append("  classDef stepStyle fill:#F0F0F0,stroke:#9E9E9E,stroke-width:1px")
        lines.append("")
        lines.append("  class " +
                     ", ".join([n.node_id for n in diagram.nodes if n.node_type == "start"]) +
                     " startStyle")
        lines.append("  class " +
                     ", ".join([n.node_id for n in diagram.nodes if n.node_type == "end"]) +
                     " endStyle")
        lines.append("  class " +
                     ", ".join([n.node_id for n in diagram.nodes if n.node_type == "scenario"]) +
                     " scenarioStyle")
        lines.append("  class " +
                     ", ".join([n.node_id for n in diagram.nodes if n.node_type == "step"]) +
                     " stepStyle")

        return "\n".join(lines)

    @handle_errors(component="journey_visualizer")
    def render_dot(self, diagram: FlowDiagram) -> str:
        """
        Render flow diagram as Graphviz DOT format

        Generates DOT syntax for advanced visualization with Graphviz.

        Args:
            diagram: Flow diagram to render

        Returns:
            DOT format string
        """
        lines = []
        lines.append("digraph JourneyFlow {")
        lines.append("  rankdir=TB;")
        lines.append("  node [fontname=\"Arial\", fontsize=12];")
        lines.append("  edge [fontname=\"Arial\", fontsize=10];")
        lines.append("")

        # Define nodes
        for node in diagram.nodes:
            label = node.label.replace('"', '\\"')
            if node.description and self.show_descriptions:
                label = f"{label}\\n{node.description}"

            # Set shape based on node type
            shapes = {
                "start": "oval",
                "end": "doubleoval",
                "scenario": "box",
                "step": "rect"
            }
            shape = shapes.get(node.node_type, "rect")

            lines.append(f'  {node.node_id} [label="{label}", shape={shape}];')

        lines.append("")

        # Define arrows
        for arrow in diagram.arrows:
            if arrow.label:
                lines.append(f'  {arrow.from_node} -> {arrow.to_node} [label="{arrow.label}"];')
            else:
                lines.append(f"  {arrow.from_node} -> {arrow.to_node};")

        lines.append("}")

        return "\n".join(lines)

    @handle_errors(component="journey_visualizer")
    def render_json(self, diagram: FlowDiagram) -> str:
        """
        Render flow diagram as structured JSON

        Args:
            diagram: Flow diagram to render

        Returns:
            JSON string representation
        """
        import json
        return json.dumps(diagram.to_dict(), indent=2)

    def render(
        self,
        diagram: FlowDiagram,
        output_format: Optional[DiagramFormat] = None
    ) -> str:
        """
        Render flow diagram in specified format

        Args:
            diagram: Flow diagram to render
            output_format: Format to render (uses default if not specified)

        Returns:
            Rendered diagram string
        """
        format_type = output_format or self.default_format

        self.logger.info(f"Rendering diagram in format: {format_type}")

        if format_type == DiagramFormat.ASCII:
            return self.render_ascii(diagram)
        elif format_type == DiagramFormat.MERMAID:
            return self.render_mermaid(diagram)
        elif format_type == DiagramFormat.DOT:
            return self.render_dot(diagram)
        elif format_type == DiagramFormat.JSON:
            return self.render_json(diagram)
        else:
            raise AdapterError(f"Unsupported format: {format_type}")

    @handle_errors(component="journey_visualizer")
    def generate_and_render(
        self,
        journey: Journey,
        output_format: Optional[DiagramFormat] = None
    ) -> Tuple[FlowDiagram, str]:
        """
        Generate and render flow diagram in one step

        Convenience method that generates and renders a diagram.

        Args:
            journey: Journey to visualize
            output_format: Format to render (uses default if not specified)

        Returns:
            Tuple of (FlowDiagram, rendered_string)
        """
        diagram = self.generate_flow_diagram(journey, output_format)
        rendered = self.render(diagram, output_format)
        return diagram, rendered

    @handle_errors(component="journey_visualizer")
    def render_interactive_html(
        self,
        diagram: FlowDiagram,
        zoom_pan_state: Optional[ZoomPanState] = None
    ) -> str:
        """
        Render flow diagram as interactive HTML with zoom and pan controls

        This method generates a complete HTML page with embedded JavaScript
        for interactive zooming and panning of the journey diagram.

        Args:
            diagram: Flow diagram to render
            zoom_pan_state: Current zoom and pan state (defaults to 1.0, 0, 0)

        Returns:
            Complete HTML string with embedded SVG and JavaScript
        """
        if zoom_pan_state is None:
            zoom_pan_state = ZoomPanState()

        self.logger.info(
            f"Rendering interactive HTML: zoom={zoom_pan_state.zoom_level}, "
            f"pan=({zoom_pan_state.pan_x}, {zoom_pan_state.pan_y})"
        )

        # Generate SVG content
        svg_content = self._generate_svg_content(diagram, zoom_pan_state)

        # Build complete HTML page
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Journey Visualizer - {diagram.journey_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f5f5;
            overflow: hidden;
        }}

        .visualizer-container {{
            width: 100vw;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        .visualizer-header {{
            background-color: #2c3e50;
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            z-index: 1000;
        }}

        .visualizer-title {{
            font-size: 18px;
            font-weight: 600;
        }}

        .visualizer-controls {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}

        .control-button {{
            background-color: #34495e;
            color: white;
            border: 1px solid #465c71;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: background-color 0.2s;
            display: flex;
            align-items: center;
            gap: 5px;
        }}

        .control-button:hover {{
            background-color: #3d536e;
        }}

        .control-button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        .zoom-display {{
            background-color: #34495e;
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 14px;
            min-width: 80px;
            text-align: center;
        }}

        .visualizer-canvas {{
            flex: 1;
            position: relative;
            overflow: hidden;
            background-color: #ffffff;
            background-image:
                radial-gradient(circle, #e0e0e0 1px, transparent 1px);
            background-size: 20px 20px;
            cursor: grab;
        }}

        .visualizer-canvas:active {{
            cursor: grabbing;
        }}

        .diagram-container {{
            transform-origin: center center;
            transition: transform 0.1s ease-out;
        }}

        /* Node styles */
        .node {{
            cursor: pointer;
            transition: filter 0.2s;
        }}

        .node:hover {{
            filter: brightness(0.95);
        }}

        .node-rect {{
            stroke-width: 2px;
            rx: 8;
            ry: 8;
        }}

        .node-start .node-rect {{
            fill: #90EE90;
            stroke: #4CAF50;
        }}

        .node-end .node-rect {{
            fill: #87CEEB;
            stroke: #2196F3;
        }}

        .node-scenario .node-rect {{
            fill: #FFFACD;
            stroke: #FFC107;
        }}

        .node-step .node-rect {{
            fill: #F0F0F0;
            stroke: #9E9E9E;
        }}

        .node-label {{
            font-size: 14px;
            font-weight: 500;
            pointer-events: none;
        }}

        .node-description {{
            font-size: 11px;
            fill: #666;
            pointer-events: none;
        }}

        /* Arrow styles */
        .arrow {{
            stroke: #555;
            stroke-width: 2;
            fill: none;
        }}

        .arrow-label {{
            font-size: 12px;
            fill: #666;
            background-color: white;
        }}
    </style>
</head>
<body>
    <div class="visualizer-container">
        <div class="visualizer-header">
            <div class="visualizer-title">📊 {diagram.journey_name}</div>
            <div class="visualizer-controls">
                <div class="zoom-display" id="zoomDisplay">
                    {round(zoom_pan_state.zoom_level * 100)}%
                </div>
                <button class="control-button" id="zoomOutBtn" title="Zoom Out">
                    🔍− Zoom Out
                </button>
                <button class="control-button" id="zoomInBtn" title="Zoom In">
                    🔍+ Zoom In
                </button>
                <button class="control-button" id="resetBtn" title="Reset View">
                    ↺ Reset
                </button>
            </div>
        </div>
        <div class="visualizer-canvas" id="canvas">
            <div class="diagram-container" id="diagramContainer">
                {svg_content}
            </div>
        </div>
    </div>

    <script>
        // Initialize zoom/pan state from server
        const initialState = {json.dumps(zoom_pan_state.to_dict())};

        // Current state
        let state = {{
            ...initialState,
            isDragging: false,
            dragStartX: 0,
            dragStartY: 0
        }};

        // DOM elements
        const canvas = document.getElementById('canvas');
        const container = document.getElementById('diagramContainer');
        const zoomInBtn = document.getElementById('zoomInBtn');
        const zoomOutBtn = document.getElementById('zoomOutBtn');
        const resetBtn = document.getElementById('resetBtn');
        const zoomDisplay = document.getElementById('zoomDisplay');

        // Apply transformation
        function applyTransform() {{
            const transform = `translate(${{state.pan_x}}px, ${{state.pan_y}}px) scale(${{state.zoom_level}})`;
            container.style.transform = transform;
            updateUI();
        }}

        // Update UI elements
        function updateUI() {{
            zoomDisplay.textContent = Math.round(state.zoom_level * 100) + '%';
            zoomInBtn.disabled = state.zoom_level >= state.max_zoom;
            zoomOutBtn.disabled = state.zoom_level <= state.min_zoom;
        }}

        // Zoom in
        function zoomIn() {{
            if (state.zoom_level < state.max_zoom) {{
                state.zoom_level = Math.min(state.zoom_level * 1.2, state.max_zoom);
                applyTransform();
            }}
        }}

        // Zoom out
        function zoomOut() {{
            if (state.zoom_level > state.min_zoom) {{
                state.zoom_level = Math.max(state.zoom_level / 1.2, state.min_zoom);
                applyTransform();
            }}
        }}

        // Reset view
        function resetView() {{
            state.zoom_level = 1.0;
            state.pan_x = 0;
            state.pan_y = 0;
            applyTransform();
        }}

        // Mouse wheel zoom
        canvas.addEventListener('wheel', (e) => {{
            e.preventDefault();
            const delta = e.deltaY > 0 ? -1 : 1;
            if (delta > 0) {{
                zoomIn();
            }} else {{
                zoomOut();
            }}
        }});

        // Drag to pan
        canvas.addEventListener('mousedown', (e) => {{
            if (e.target === canvas || e.target.tagName === 'svg') {{
                state.isDragging = true;
                state.dragStartX = e.clientX - state.pan_x;
                state.dragStartY = e.clientY - state.pan_y;
            }}
        }});

        document.addEventListener('mousemove', (e) => {{
            if (state.isDragging) {{
                state.pan_x = e.clientX - state.dragStartX;
                state.pan_y = e.clientY - state.dragStartY;
                applyTransform();
            }}
        }});

        document.addEventListener('mouseup', () => {{
            state.isDragging = false;
        }});

        // Button events
        zoomInBtn.addEventListener('click', zoomIn);
        zoomOutBtn.addEventListener('click', zoomOut);
        resetBtn.addEventListener('click', resetView);

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {{
            if (e.key === '=' || e.key === '+') {{
                e.preventDefault();
                zoomIn();
            }} else if (e.key === '-') {{
                e.preventDefault();
                zoomOut();
            }} else if (e.key === '0') {{
                e.preventDefault();
                resetView();
            }}
        }});

        // Initialize
        applyTransform();
        console.log('Journey Visualizer initialized:', state);
    </script>
</body>
</html>"""

        self.logger.info("Interactive HTML generated successfully")
        return html

    def _generate_svg_content(
        self,
        diagram: FlowDiagram,
        zoom_pan_state: ZoomPanState
    ) -> str:
        """
        Generate SVG content for the diagram

        Args:
            diagram: Flow diagram to render
            zoom_pan_state: Current zoom and pan state

        Returns:
            SVG markup string
        """
        # Calculate layout (simple tree layout)
        node_positions = self._calculate_node_positions(diagram)

        # Generate SVG elements
        svg_elements = []

        # Add arrows first (so they appear behind nodes)
        for arrow in diagram.arrows:
            svg_elements.append(self._render_svg_arrow(arrow, node_positions))

        # Add nodes
        for node in diagram.nodes:
            svg_elements.append(self._render_svg_node(node, node_positions))

        # Wrap in SVG tag
        svg_width = max(800, len(diagram.nodes) * 200)
        svg_height = max(600, len(diagram.nodes) * 120)

        svg = f"""<svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#555" />
        </marker>
    </defs>
    {chr(10).join(svg_elements)}
</svg>"""

        return svg

    def _calculate_node_positions(
        self,
        diagram: FlowDiagram
    ) -> Dict[str, Tuple[float, float]]:
        """
        Calculate node positions for diagram layout

        Args:
            diagram: Flow diagram

        Returns:
            Dictionary mapping node IDs to (x, y) positions
        """
        positions = {}
        node_width = 180
        node_height = 60
        horizontal_spacing = 50
        vertical_spacing = 100

        # Group nodes by type for layout
        start_nodes = [n for n in diagram.nodes if n.node_type == "start"]
        scenario_nodes = [n for n in diagram.nodes if n.node_type == "scenario"]
        step_nodes = [n for n in diagram.nodes if n.node_type == "step"]
        end_nodes = [n for n in diagram.nodes if n.node_type == "end"]

        y = 50

        # Position start node
        for node in start_nodes:
            x = 400
            positions[node.node_id] = (x, y)
            y += node_height + vertical_spacing

        # Position scenario nodes
        for idx, node in enumerate(scenario_nodes):
            x = 200 + (idx % 3) * (node_width + horizontal_spacing)
            if idx > 0 and idx % 3 == 0:
                y += node_height + vertical_spacing
            positions[node.node_id] = (x, y)

            # Position step nodes for this scenario
            scenario_steps = [
                n for n in step_nodes
                if n.node_id.startswith(node.node_id + "_step")
            ]
            step_y = y + node_height + vertical_spacing
            for step_idx, step_node in enumerate(scenario_steps):
                step_x = x
                positions[step_node.node_id] = (step_x, step_y)
                step_y += node_height + vertical_spacing

            y += node_height + vertical_spacing

        # Position end node
        for node in end_nodes:
            x = 400
            positions[node.node_id] = (x, y)

        return positions

    def _render_svg_node(
        self,
        node: FlowNode,
        positions: Dict[str, Tuple[float, float]]
    ) -> str:
        """
        Render a single node as SVG

        Args:
            node: Node to render
            positions: Calculated node positions

        Returns:
            SVG markup for the node
        """
        if node.node_id not in positions:
            return ""

        x, y = positions[node.node_id]
        width = 180
        height = 60

        label_lines = self._wrap_text(node.label, 20)
        label_y = y + 25

        svg_parts = [
            f'<g class="node node-{node.node_type}" data-node-id="{node.node_id}">',
            f'  <rect class="node-rect" x="{x}" y="{y}" width="{width}" height="{height}" />',
            f'  <text class="node-label" x="{x + width/2}" y="{label_y}" text-anchor="middle">'
        ]

        for line_idx, line in enumerate(label_lines):
            line_y = label_y + (line_idx * 16)
            svg_parts.append(f'    <tspan x="{x + width/2}" dy="{line_idx * 16}">{line}</tspan>')

        svg_parts.append('  </text>')

        if node.description:
            svg_parts.append(
                f'  <text class="node-description" x="{x + width/2}" y="{y + height - 10}" text-anchor="middle">'
                f'{node.description[:30]}...</text>'
            )

        svg_parts.append('</g>')

        return "\n    ".join(svg_parts)

    def _render_svg_arrow(
        self,
        arrow: FlowArrow,
        positions: Dict[str, Tuple[float, float]]
    ) -> str:
        """
        Render a single arrow as SVG

        Args:
            arrow: Arrow to render
            positions: Calculated node positions

        Returns:
            SVG markup for the arrow
        """
        if arrow.from_node not in positions or arrow.to_node not in positions:
            return ""

        from_x, from_y = positions[arrow.from_node]
        to_x, to_y = positions[arrow.to_node]

        # Adjust for node dimensions
        from_x += 90  # Half of node width
        from_y += 60  # Node height
        to_x += 90
        to_y

        # Calculate path
        mid_y = (from_y + to_y) / 2
        path_d = f"M {from_x} {from_y} L {from_x} {mid_y} L {to_x} {mid_y} L {to_x} {to_y}"

        svg = f'<path class="arrow" d="{path_d}" marker-end="url(#arrowhead)" />'

        if arrow.label:
            label_x = (from_x + to_x) / 2
            label_y = mid_y
            svg += f'\n    <text class="arrow-label" x="{label_x}" y="{label_y}" text-anchor="middle">{arrow.label}</text>'

        return svg

    def _wrap_text(self, text: str, max_chars: int) -> List[str]:
        """
        Wrap text to fit within node width

        Args:
            text: Text to wrap
            max_chars: Maximum characters per line

        Returns:
            List of text lines
        """
        if len(text) <= max_chars:
            return [text]

        lines = []
        current_line = ""
        words = text.split()

        for word in words:
            if len(current_line + " " + word) <= max_chars:
                current_line += (" " if current_line else "") + word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    # ============================================================================
    # Dependency Visualization Methods (Feature #164)
    # ============================================================================

    @handle_errors(component="journey_visualizer", reraise=True)
    def build_dependency_graph(self, journey: Journey) -> DependencyGraph:
        """
        Build dependency graph from journey scenarios

        Args:
            journey: Journey containing scenarios with dependencies

        Returns:
            DependencyGraph with nodes, edges, and critical path
        """
        self.logger.info(f"Building dependency graph for journey: {journey.name}")

        # Create graph
        graph = DependencyGraph(
            journey_id=journey.journey_id,
            journey_name=journey.name
        )

        # Create nodes from scenarios
        for scenario in journey.scenarios:
            node = ScenarioNode(
                scenario_id=scenario.scenario_id,
                name=scenario.name,
                description=scenario.description,
                depends_on=scenario.dependencies.copy()
            )
            graph.nodes[scenario.scenario_id] = node

        # Create edges and build dependents list
        for scenario in journey.scenarios:
            for dep_id in scenario.dependencies:
                if dep_id in graph.nodes:
                    # Create edge
                    edge = DependencyEdge(
                        from_scenario_id=dep_id,
                        to_scenario_id=scenario.scenario_id
                    )
                    graph.edges.append(edge)

                    # Update dependents
                    if scenario.scenario_id not in graph.nodes[dep_id].dependents:
                        graph.nodes[dep_id].dependents.append(scenario.scenario_id)

        # Identify critical path
        graph.critical_path = self._identify_critical_path(graph)

        # Mark nodes on critical path
        for scenario_id in graph.critical_path:
            if scenario_id in graph.nodes:
                graph.nodes[scenario_id].is_on_critical_path = True

        # Calculate dependency levels for edges
        self._calculate_dependency_levels(graph)

        self.logger.info(
            f"Built graph with {len(graph.nodes)} nodes, "
            f"{len(graph.edges)} edges, critical path length: {len(graph.critical_path)}"
        )

        return graph

    def _identify_critical_path(self, graph: DependencyGraph) -> List[str]:
        """
        Identify the critical path (longest dependency chain)

        Uses topological sort and longest path algorithm.

        Args:
            graph: Dependency graph

        Returns:
            List of scenario IDs in critical path order
        """
        if not graph.nodes:
            return []

        # Calculate longest distance to each node
        distance = {node_id: 0 for node_id in graph.nodes}
        predecessor = {node_id: None for node_id in graph.nodes}

        # Process nodes in topological order
        visited: Set[str] = set()
        stack: List[str] = list(graph.nodes.keys())

        while stack:
            node_id = stack.pop(0)

            if node_id in visited:
                continue

            visited.add(node_id)

            # Update distances to dependents
            for dependent_id in graph.nodes[node_id].dependents:
                if distance[node_id] + 1 > distance[dependent_id]:
                    distance[dependent_id] = distance[node_id] + 1
                    predecessor[dependent_id] = node_id

        # Find node with maximum distance (end of critical path)
        max_distance = max(distance.values())
        end_nodes = [nid for nid, dist in distance.items() if dist == max_distance]

        # Build critical path by backtracking from end node
        critical_path: List[str] = []
        current = end_nodes[0] if end_nodes else None

        while current is not None:
            critical_path.insert(0, current)
            current = predecessor[current]

        return critical_path

    def _calculate_dependency_levels(self, graph: DependencyGraph) -> None:
        """
        Calculate dependency impact levels for edges

        Args:
            graph: Dependency graph (modified in place)
        """
        # Count how many scenarios each dependency blocks
        blocks_count: Dict[str, int] = {}

        for node_id, node in graph.nodes.items():
            blocks_count[node_id] = len(node.dependents)

        # Determine levels based on blocks count and critical path
        for edge in graph.edges:
            # Critical path edges are CRITICAL
            if (edge.from_scenario_id in graph.critical_path and
                edge.to_scenario_id in graph.critical_path):
                edge.level = DependencyLevel.CRITICAL
            # High blocking count is HIGH
            elif blocks_count[edge.from_scenario_id] >= 3:
                edge.level = DependencyLevel.HIGH
            # Medium blocking count is MEDIUM
            elif blocks_count[edge.from_scenario_id] >= 2:
                edge.level = DependencyLevel.MEDIUM
            # Low blocking count is LOW
            else:
                edge.level = DependencyLevel.LOW

    @handle_errors(component="journey_visualizer")
    def visualize_dependencies_text(self, graph: DependencyGraph) -> str:
        """
        Generate text-based visualization of dependency graph

        Args:
            graph: Dependency graph

        Returns:
            Text representation with ASCII arrows
        """
        lines = []
        lines.append(f"Dependency Graph: {graph.journey_name}")
        lines.append("=" * 70)
        lines.append("")

        # Show nodes
        lines.append("Scenarios:")
        for node_id, node in graph.nodes.items():
            critical_marker = " ⚡ CRITICAL" if node.is_on_critical_path else ""
            lines.append(f"  • {node.name} ({node.scenario_id}){critical_marker}")

            if node.depends_on:
                for dep_id in node.depends_on:
                    dep_node = graph.nodes.get(dep_id)
                    dep_name = dep_node.name if dep_node else dep_id
                    lines.append(f"      depends on → {dep_name}")
            else:
                lines.append(f"      (no dependencies)")

        lines.append("")

        # Show critical path
        if graph.critical_path:
            lines.append("Critical Path:")
            path_names = []
            for scenario_id in graph.critical_path:
                node = graph.nodes.get(scenario_id)
                name = node.name if node else scenario_id
                path_names.append(name)

            lines.append("  → ".join(path_names))

        lines.append("")

        return "\n".join(lines)

    @handle_errors(component="journey_visualizer")
    def visualize_dependencies_mermaid(self, graph: DependencyGraph) -> str:
        """
        Generate Mermaid diagram for dependency graph

        Args:
            graph: Dependency graph

        Returns:
            Mermaid diagram string
        """
        lines = []
        lines.append("graph TD")

        # Define nodes
        for node_id, node in graph.nodes.items():
            label = node.name.replace('"', '\\"')
            if node.is_on_critical_path:
                lines.append(f'    {node_id}["{label}"]:::critical')
            else:
                lines.append(f'    {node_id}["{label}"]')

        # Define edges
        for edge in graph.edges:
            if edge.level == DependencyLevel.CRITICAL:
                lines.append(f'    {edge.from_scenario_id} ==>|Critical| {edge.to_scenario_id}')
            elif edge.level == DependencyLevel.HIGH:
                lines.append(f'    {edge.from_scenario_id} -->|High| {edge.to_scenario_id}')
            elif edge.level == DependencyLevel.MEDIUM:
                lines.append(f'    {edge.from_scenario_id} -->|Medium| {edge.to_scenario_id}')
            else:
                lines.append(f'    {edge.from_scenario_id} -->|Low| {edge.to_scenario_id}')

        # Add styling
        lines.append("")
        lines.append("    classDef critical fill:#ff9900,stroke:#ff6600,stroke-width:3px")

        return "\n".join(lines)

    @handle_errors(component="journey_visualizer")
    def generate_dependency_visualization(
        self,
        journey: Journey,
        output_format: str = "text"
    ) -> Tuple[DependencyGraph, str]:
        """
        Generate complete dependency visualization for a journey

        Args:
            journey: Journey with scenarios and dependencies
            output_format: Format for visualization ("text", "mermaid", "html")

        Returns:
            Tuple of (DependencyGraph, visualization_string)
        """
        graph = self.build_dependency_graph(journey)

        if output_format == "text":
            visualization = self.visualize_dependencies_text(graph)
        elif output_format == "mermaid":
            visualization = self.visualize_dependencies_mermaid(graph)
        else:
            visualization = self.visualize_dependencies_text(graph)

        return graph, visualization
