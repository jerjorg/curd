"""Data structures for curriculum design"""

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple
from networkx import (
    chordless_cycles,
    immediate_dominators,
    transitive_closure,
    transitive_reduction,
    DiGraph,
)

import pydot
import random

import antichains


@dataclass(order=True, frozen=True)
class Requirement:
    "An requirement of a course"

    name: str


@dataclass(order=True, frozen=True)
class CourseId:
    """An immutable object that contains just a course code. It is hashable and
    can be used in a `networkx.DiGraph` object."""

    dept: str
    course_number: str

    def __str__(self) -> str:
        return f"{self.dept}_{self.course_number}"

    def to_tuple(self) -> Tuple[str, str]:
        """Produce a tuple; useful for serialization."""
        return (self.dept, self.course_number)

    @staticmethod
    def from_tuple(t: Tuple[str, str]) -> "CourseId":
        """Produce a CourseId from a tuple; useful for deserialization."""
        return CourseId(t[0], t[1])

    @staticmethod
    def from_str(s: str) -> "CourseId":
        pieces = s.split("_")
        assert len(pieces) == 2
        id_tuple = (pieces[0], pieces[1])
        return CourseId.from_tuple(id_tuple)

    def is_elective(self) -> bool:
        """Determine if this course can be used as an elective.

        For now, this is hard-coded for UVU's requirements. Consider creating a
        more general way to express this.
        """
        return (
            self.dept == "CS"
            and len(self.course_number) > 0
            and (int(self.course_number[0]) >= 3 or self.course_number == "2700")
        )


@dataclass(order=True)
class Course:
    "A college course"

    c_id: CourseId
    title: str
    creds: int


@dataclass(order=True, frozen=True)
class ProgramId:
    """An immutable object that contains just a program name. It is hashable
    and can be used in a `networkx.DiGraph` object."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(order=True)
class Program:
    "A degree or emphasis"

    p_id: ProgramId
    requirements: set[Requirement]

    def fits(self, limits: "Limits"):
        """Determine if the program fits within the specified credit and term
        limits."""
        # TODO
        return self is not None and limits is not None


@dataclass(order=True, frozen=True)
class Limits:
    "The limits on credits and terms for a Catalog"

    program_credit_limit: int = 120
    term_credit_limit: int = 18
    terms: int = 8
    terms_past: int = 0


@dataclass
class CycleException(ValueError):
    cycles: list[list[CourseId]]


@dataclass
class Catalog:
    "A course catalog"

    requirements: set[Requirement]
    requirement_deps: Dict[Requirement, set[Requirement]]
    courses: Dict[CourseId, Course]
    course_requirements: Dict[Requirement, set[CourseId]]
    programs: Dict[ProgramId, Program]
    limits: Limits
    selections: set[CourseId]
    constraints: list[set[Tuple[str, antichains.Op, str | int]]]

    @staticmethod
    def _check(d: DiGraph) -> list[list[CourseId]]:
        return sorted(list(chordless_cycles(d)))

    @staticmethod
    def bottlenecks(d: DiGraph):
        flow = d.copy()
        flow.add_node("source")
        for node in d.nodes:
            if d.in_degree(node) == 0:
                flow.add_edge("source", node)
            if d.out_degree(node) == 0:
                flow.add_edge(node, "sink")
        dom_tree = immediate_dominators(flow, "source")
        bottlenecks = {dom_tree["sink"]}
        print(bottlenecks)
        frontier = set(bottlenecks)
        while frontier:
            node = frontier.pop()
            dom = dom_tree[node]
            if dom == "source" or dom in bottlenecks:
                continue
            bottlenecks.add(node)
            frontier.add(node)
        return bottlenecks

    def reqs_graph(self) -> DiGraph:
        """Create a `networkx.DiGraph` object to show the relationships between
        requirements."""
        result: DiGraph = DiGraph()
        for post, pres in self.requirement_deps.items():
            for pre in pres:
                result.add_edge(pre, post)
        return Catalog.reduce_graph(result)

    def prereq_requirements(self, c_id: CourseId) -> set[Requirement]:
        """The requirements that must be met before taking `c_id`: those that the
        requirements it satisfies depend on, other than ones it meets itself."""
        deps = {
            dep
            for req, c_ids in self.course_requirements.items()
            if c_id in c_ids
            for dep in self.requirement_deps.get(req, ())
        }
        return {dep for dep in deps if c_id not in self.course_requirements.get(dep, ())}

    def select_courses(self, p_id: str | ProgramId) -> Tuple[set[CourseId], set[CourseId]]:
        """
        Select courses sufficient to match every requirement. When there are
        multiple options, choose randomly between them."""
        if isinstance(p_id, str):
            p_id = ProgramId(p_id)
        program = self.programs[p_id]

        pre_select = set(self.selections)
        required: set[CourseId] = set()

        requirements = program.requirements
        gens = ProgramId("generals")
        if gens in self.programs:
            requirements |= self.programs[gens].requirements

        for requirement in program.requirements:
            courses = self.course_requirements[requirement]
            pre = pre_select & courses
            if pre:
                choice = pre.pop()
                pre_select.remove(choice)
                required.add(choice)
                continue
            if required & courses:
                continue
            required.add(random.choice(list(courses)))
        total_required = sum(map(lambda c: self.courses[c].creds, required))

        electives: set[CourseId] = pre_select
        total_elective = sum(
            map(
                lambda c: self.courses[c].creds,
                filter(lambda c: c.is_elective(), pre_select),
            )
        )
        elective_options = list(
            filter(
                lambda cid: cid.is_elective(),
                set(self.courses) - (required | electives),
            )
        )
        random.shuffle(elective_options)
        while total_elective < self.limits.program_credit_limit - total_required:
            # Only take an elective whose prerequisites are among the courses chosen so far
            chosen = required | electives
            ready = [
                c
                for c in elective_options
                if all(self.course_requirements.get(dep, set()) & chosen for dep in self.prereq_requirements(c))
            ]
            if not ready:
                print("Warning: insufficient electives to complete the program")
                break
            selection = ready[-1]
            elective_options.remove(selection)
            electives.add(selection)
            total_elective += self.courses[selection].creds

        total = total_required + total_elective

        if total > self.limits.program_credit_limit:
            print(
                f"Warning: the courses selected total {total} credits but the "
                "specified credit limit for a program is "
                f"{self.limits.program_credit_limit}."
            )

        return (required, electives)

    def build_courses_graph(self, courses: Optional[set[CourseId]] = None) -> DiGraph:
        """Induce a `networkx.DiGraph` representing the prerequisite
        dependencies between the specified courses. The resulting graph is the
        transitive _reduction_ of the relationships between classes. If the
        resulting graph is cyclic, raise a `CycleException` containing the
        courses that create the cycle."""
        result: DiGraph = DiGraph()
        if courses is None:
            courses = set()
        for requirement, deps in self.requirement_deps.items():
            for post_course in self.course_requirements[requirement]:
                for dep in deps:
                    for pre_course in self.course_requirements[dep]:
                        if post_course != pre_course:
                            result.add_edge(pre_course, post_course)
        result = Catalog.close_graph(result)
        if courses:
            result = result.subgraph(courses)  # type: ignore
        return Catalog.reduce_graph(result)

    def blocking_factors(self, courses: Optional[set[CourseId]] = None) -> dict[CourseId, int]:
        graph = self.build_courses_graph(courses)
        result: dict[CourseId, int] = {}
        for course, block_factor in graph.out_degree():
            result[course] = int(block_factor)
        return result

    def centrality_factors(self, courses: Optional[set[CourseId]] = None) -> dict[CourseId, int]:
        graph = self.build_courses_graph(courses)
        result: dict[CourseId, int] = {}
        for course, centrality_factor in graph.in_degree():
            result[course] = int(centrality_factor)
        return result

    @staticmethod
    def reduce_graph(graph: DiGraph) -> DiGraph:
        """Check for cycles in `graph`. If it is cyclic, return the cycles.
        Otherwise, return its transitive reduction."""
        cycles = Catalog._check(graph)
        if cycles:
            raise CycleException(cycles)
        return transitive_reduction(graph)  # type: ignore

    @staticmethod
    def close_graph(graph: DiGraph) -> DiGraph:
        """Check for cycles in `graph`. If it is cyclic, return the cycles.
        Otherwise, return its transitive closure."""
        cycles = Catalog._check(graph)
        if cycles:
            raise CycleException(cycles)
        return transitive_closure(graph)  # type: ignore

    def add_course(self, dept: str, course_number: str, title: str, creds: int):
        """Add a course to the catalog. If another course by the same
        department and course number exists, replace it."""
        c_id = CourseId(dept, course_number)
        self.courses[c_id] = Course(c_id, title, creds)

    @staticmethod
    def _get_requirement(req: str | Requirement) -> Requirement:
        match req:
            case str():
                return Requirement(req)
            case Requirement():
                return req
            case _:
                raise TypeError(f"Cannot make an Requirement from {req}")

    @staticmethod
    def _get_program(program: str | ProgramId) -> ProgramId:
        match program:
            case str():
                return ProgramId(program)
            case ProgramId():
                return program
            case _:
                raise TypeError(f"Cannot make a ProgramId from {program}")

    @staticmethod
    def _get_course(course: str | Tuple[str, str] | CourseId) -> CourseId:
        match course:
            case str(name):
                values = name.split()
                assert len(values) == 2
                dept, course_number = values
                return CourseId(dept, course_number)
            case (str(dept), str(course_number)):
                return CourseId(dept, course_number)
            case CourseId():
                return course
            case _:
                raise TypeError(f"Cannot make a CourseId from {course}")

    def add_requirement(
        self,
        req: str | Requirement,
        courses: Iterable[str | Tuple[str, str] | CourseId],
    ):
        """Add a requirement to the catalog, which can be satisfied by any
        course in `courses`."""
        course_ids = set(map(Catalog._get_course, courses))
        req = Catalog._get_requirement(req)
        self.requirements.add(req)
        assert req not in self.course_requirements
        self.course_requirements[req] = set(course_ids)

    def req_depends(self, pre_req: str | Requirement, post_req: str | Requirement):
        """Add a dependency between two requirements. Both requirements must
        already be in the catalog.

        All prerequisites must be satisfied before enrolling in a course. If
        students can choose between courses, create a requirement that can be
        satisfied by any of them."""
        pre_req = Catalog._get_requirement(pre_req)
        post_req = Catalog._get_requirement(post_req)
        assert pre_req in self.requirements and post_req in self.requirements
        self.requirement_deps.setdefault(post_req, set()).add(pre_req)

    def add_program(
        self,
        name: str | ProgramId,
        requirements: Optional[Iterable[str | Requirement]] = None,
    ):
        """Add a program to the catalog. Requirements may optionally be
        specified that pertain to the program."""
        reqs: set[Requirement] = set()
        if requirements is not None:
            reqs = set(map(Catalog._get_requirement, requirements))
        p_id = Catalog._get_program(name)
        self.programs[p_id] = Program(p_id, reqs)

    def add_requirement_to_program(self, name: str | ProgramId, requirement: str | Requirement):
        """Add a requirement to the specified program. If no such requirement
        exists in the catalog, create it."""
        p_id = Catalog._get_program(name)
        req = Catalog._get_requirement(requirement)
        self.programs.setdefault(p_id, Program(p_id, set())).requirements.add(req)

    def get_scheduler(self, p_id: str | ProgramId) -> antichains.Scheduler:
        required, electives = self.select_courses(p_id)
        courses = required | electives
        prereqs = list(self.build_courses_graph(courses).edges())

        def course_value(c_id: CourseId) -> Tuple[CourseId, int]:
            return c_id, self.courses[c_id].creds

        return antichains.Scheduler(
            map(course_value, courses),
            prereqs,
            self.limits.terms,
            self.limits.term_credit_limit,
            self.limits.terms_past,
            required,
            self.constraints,
        )

    def generate_schedule(self, p_id: str | ProgramId) -> antichains.Schedule:
        """Choose classes that satisfy the program's requirements (using
        `Catalog.select_courses()`) and put them in a schedule with the
        appropriate number of terms."""

        scheduler = self.get_scheduler(p_id)
        return scheduler.generate_schedule()

    def generate_graph(self, p_id: str | ProgramId) -> pydot.Graph:
        scheduler = self.get_scheduler(p_id)
        return self.dot(scheduler.generate_schedule(), scheduler.required)

    def dot(
        self,
        schedule: antichains.Schedule,
        required: set[CourseId],
    ) -> pydot.Graph:
        graph = pydot.Dot("schedule", graph_type="digraph", compound="true", rankdir="LR")
        nodes: dict[CourseId, pydot.Node] = {}
        terms: dict[CourseId, int] = {}
        last = None
        for index, (total, classes) in enumerate(schedule.schedule):
            term = index + 1
            credit_total = 0
            for c in classes:
                credit_total += self.courses[c].creds
            subgraph = pydot.Subgraph(
                f"cluster_term_{term}",
                label=f"Term {term} ({credit_total})",
                rankdir="TB",
            )
            graph.add_subgraph(subgraph)
            for c in sorted(classes):
                terms[c] = term
                nodes[c] = pydot.Node(str(c), shape="box")
                if c not in required:
                    nodes[c].set("style", "dashed")
                subgraph.add_node(nodes[c])
            if last:
                graph.add_edge(
                    pydot.Edge(
                        last.get_nodes()[0],
                        subgraph.get_nodes()[0],
                        ltail=last.get_name(),
                        lhead=subgraph.get_name(),
                        style="invis",
                    )
                )
            last = subgraph
        return graph
