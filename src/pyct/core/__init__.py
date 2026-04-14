from __future__ import annotations

import builtins
from typing import Any

# Type aliases
SymbolicExpression = str | list[Any]
Engine = Any


class Concolic:
    """
    Mixin class for concolic execution support.

    This mixin adds symbolic execution capabilities to Python's built-in types.
    It tracks both concrete values and symbolic expressions for constraint solving.

    The mixin is designed to work with immutable types (int, bool, str, float)
    using Python's standard __new__/__init__ pattern.

    Attributes:
        value: SMT-LIB2 representation of the concrete value
        expr: Symbolic expression or concrete value
        engine: Reference to the concolic execution engine

    Usage:
        class ConcolicInt(int, Concolic):
            def __new__(cls, value, expr=None, engine=None):
                instance = int.__new__(cls, value)
                return instance

            def __init__(self, value, expr=None, engine=None):
                super().__init__(expr=expr, engine=engine)
    """

    def __init__(
        self,
        expr: SymbolicExpression | None = None,
        engine: Engine | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize concolic mixin attributes.

        This method is called after __new__ creates the object. It doesn't
        take 'value' as a parameter because the concrete value is already
        set by the immutable type's __new__ method.

        Args:
            expr: Symbolic expression representing this value
            engine: Execution engine for path tracking
            **kwargs: Additional arguments (passed to super().__init__)

        Note:
            The concrete value is extracted from self using _get_concrete_value()
        """
        # Call next in MRO (important for cooperative multiple inheritance)
        super().__init__(**kwargs)

        # Get the concrete value that was already set by __new__
        concrete_value = self._get_concrete_value()

        # Import here to avoid circular dependencies
        from pyct.utils.smt_converter import py2smt

        # Resolve engine, value, and expression
        self.engine = self._resolve_engine(engine, expr, concrete_value)
        self.value = py2smt(concrete_value)
        self.expr = self._resolve_expression(expr, self.value)

    def _get_concrete_value(self) -> Any:
        """
        Extract the concrete value from self.

        This method retrieves the primitive value that was set by the
        immutable type's __new__ method. It uses the base type's methods
        to avoid calling overridden magic methods.

        Returns:
            Concrete primitive value
        """
        # Use base type methods to get unwrapped value
        # Note: Concolic subclasses (ConcolicBool, ConcolicInt, etc.) inherit
        # from both Concolic and the primitive type, so these checks are valid
        # at runtime even though the type checker can't see the multiple inheritance.
        if isinstance(self, builtins.bool):  # pyright: ignore[reportUnnecessaryIsInstance]
            # bool is a subclass of int, check it first
            return builtins.bool.__bool__(self)
        elif isinstance(self, builtins.int):
            return builtins.int.__int__(self)
        elif isinstance(self, builtins.float):
            return builtins.float.__float__(self)
        elif isinstance(self, builtins.str):
            return builtins.str.__str__(self)
        else:
            # Fallback for other types
            return self

    def _resolve_engine(
        self,
        engine: Engine | None,
        expr: SymbolicExpression | None,
        value: Any,
    ) -> Engine | None:
        """
        Determine which execution engine to use.

        Resolution order:
        1. Use explicitly provided engine
        2. Find engine embedded in the expression
        3. Validate expression with Solver
        4. Return None (concrete execution)

        Args:
            engine: Explicitly provided engine
            expr: Symbolic expression to search
            value: Concrete value for validation

        Returns:
            Resolved engine or None
        """
        if engine is not None:
            return engine

        if expr is not None:
            found_engine = self.find_engine_in_expr(expr)
            if found_engine is not None:
                return found_engine

        return self._validate_with_solver(expr, value)

    @staticmethod
    def _validate_with_solver(expr: SymbolicExpression | None, value: Any) -> Engine | None:
        """Validate expression via the engine's solver instance.

        Attempts to find an engine embedded in *expr* and, if the engine
        owns a solver, delegates to ``solver.validate_expression``.
        """
        engine = Concolic.find_engine_in_expr(expr)
        if engine is None:
            return None
        solver = getattr(engine, "solver", None)
        if solver is None:
            return None
        return solver.validate_expression(expr, value)

    def _resolve_expression(
        self,
        expr: SymbolicExpression | None,
        concrete_value: str,
    ) -> str | list[Any]:
        """
        Determine which expression to use.

        Args:
            expr: Symbolic expression
            concrete_value: SMT-LIB2 representation of concrete value

        Returns:
            Symbolic expression or concrete value
        """
        if expr is not None and self.engine is not None:
            return expr
        return concrete_value

    @staticmethod
    def find_engine_in_expr(expr: Concolic | list | Any) -> Engine | None:
        """
        Recursively search for an execution engine in an expression tree.

        Args:
            expr: Expression to search (Concolic, List, or other)

        Returns:
            First engine found, or None

        Examples:
            >>> cb = ConcolicBool(True, "x", engine)
            >>> Concolic.find_engine_in_expr(cb)
            <Engine instance>

            >>> expr = ["and", cb1, ["or", cb2, "y"]]
            >>> Concolic.find_engine_in_expr(expr)
            <Engine instance>
        """
        if isinstance(expr, Concolic):
            return expr.engine

        if isinstance(expr, list):
            for element in expr:
                engine = Concolic.find_engine_in_expr(element)
                if engine is not None:
                    return engine

        return None

    def is_symbolic(self) -> bool:
        """Check if this object has symbolic representation."""
        return self.engine is not None and self.expr != self.value

    def is_concrete(self) -> bool:
        """Check if this object is purely concrete."""
        return not self.is_symbolic()

    def __getstate__(self) -> dict:
        """
        Get state for pickling, excluding unpicklable engine reference.

        Returns:
            Dictionary of picklable state
        """
        state = self.__dict__.copy()
        # Remove the engine reference which contains RLocks
        state["engine"] = None
        return state

    def __setstate__(self, state: dict) -> None:
        """
        Restore state from pickling.

        Args:
            state: Dictionary of state to restore
        """
        self.__dict__.update(state)

    def __repr__(self) -> str:
        """Developer-friendly representation."""
        mode = "symbolic" if self.is_symbolic() else "concrete"
        return f"<Concolic({mode}): value={self.value}, expr={self.expr}>"


class MetaFinal(type):
    """
    Metaclass that prevents subclassing (final classes).

    Examples:
        >>> class FinalClass(metaclass=MetaFinal):
        ...     pass

        >>> class Subclass(FinalClass):  # Raises TypeError
        ...     pass
    """

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        classdict: dict[str, Any],
    ) -> type:
        """Create a new class, preventing subclassing of final classes.

        This implementation avoids using isinstance(..., cls) which can trigger
        type-checker diagnostics when 'cls' is a metaclass. Instead it checks
        the base's metaclass identity and an optional explicit "__final__"
        marker on the base class.
        """
        for base in bases:
            # If the base's metaclass is exactly this metaclass, treat the base
            # as final and disallow subclassing.
            if type(base) is cls:
                base_name = getattr(base, "__name__", repr(base))
                raise TypeError(
                    f"Cannot subclass final type '{base_name}'. "
                    + "The class is marked as final and does not support inheritance."
                )

            # Support an explicit marker on classes to mark them as final.
            if getattr(base, "__final__", False):
                base_name = getattr(base, "__name__", repr(base))
                raise TypeError(
                    f"Cannot subclass final type '{base_name}'. "
                    + "The class is marked as final and does not support inheritance."
                )

        return type.__new__(cls, name, bases, dict(classdict))


# ============================================================================
# Helper Functions
# ============================================================================


def is_concolic(obj: Any) -> bool:
    """Check if an object is a concolic type."""
    return isinstance(obj, Concolic)


def has_symbolic_expression(obj: Any) -> bool:
    """Check if an object has a symbolic expression."""
    return is_concolic(obj) and obj.is_symbolic()
