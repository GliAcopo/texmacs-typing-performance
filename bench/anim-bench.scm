;; Loaded by anim-bench.py.  F11: cursor to body paragraph TMANIM_PAR; F10: cursor just
;; after the first <video> (the driver then leaves the figure with Down).  Touches TMANIM_READY when idle.
(define (anim-first-video t)
  (cond ((tree-is? t 'video) t)
        ((tree-atomic? t) #f)
        (else (let loop ((i 0))
                (and (< i (tree-arity t))
                     (or (anim-first-video (tree-ref t i)) (loop (+ i 1))))))))
(define (anim-go-par)
  (let* ((body (buffer-tree))
         (i (min (- (tree-arity body) 1)
                 (string->number (or (getenv "TMANIM_PAR") "30")))))
    (tree-go-to (tree-ref body i) :end)))
(define (anim-go-video)
  (let ((v (anim-first-video (buffer-tree))))
    (when v (tree-go-to v :end))))
(kbd-map ("F11" (anim-go-par))
         ("F10" (anim-go-video)))
(delayed
  (:idle 2000)
  (anim-go-par)
  (delayed
    (:idle 3000)
    (system (string-append "touch '" (getenv "TMANIM_READY") "'"))))
